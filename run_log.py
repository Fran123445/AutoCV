"""
Run telemetry: what a stage did, posting by posting and call by call.

Two halves that never touch the same objects. The recording half is what the
worker threads use: a ContextVar holding the current posting's call list, so
llm.client can log a call without every task having to pass a run id down.
The writing half is RunLogger, which owns the only connection and runs on the
main thread. Finished postings cross between the two on a queue, because sqlite
takes one writer and the transform stage has MAX_CONCURRENCY of them.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone

import hashlib
import json
import queue
import sqlite3
import subprocess

from db_creation import DB_PATH, ROOT_DIR
from llm.config import BASE_URL, MODEL_NAME, TEMPERATURE, TIMEOUT


def utc_now() -> str:
    """
    Current time as an ISO 8601 string.

    Seconds precision and explicit UTC, so the run columns sort as text the way
    the date columns on FactJob already do.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def prompt_fingerprint(prompt: str) -> str:
    """
    Hash a rendered prompt so runs can be compared across prompt edits.

    Args:
        prompt (str): The prompt as it was sent, registry lists included.

    Returns:
        str: Hex digest. sha1 because this identifies a prompt, it does not
            protect one: nothing here is adversarial and the digest is short
            enough to read in a query result.
    """
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()


@dataclass
class LLMCall:
    """One request to the model. Mirrors a FactLLMCall row."""

    task_name: str
    started_at: str
    ended_at: str | None = None
    latency_ms: int | None = None
    model_name: str | None = None
    temperature: float | None = None
    think: bool | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_sha1: str | None = None
    http_status: int | None = None
    status: str = "running"
    error: str | None = None


@dataclass
class JobRun:
    """One posting inside one run, with the calls it made. A FactJobRun row."""

    source_file: str
    started_at: str
    ended_at: str | None = None
    status: str = "running"
    error: str | None = None
    # Filled by the load stage once the posting has a FactJob row. Stays null
    # through extract and transform, where the posting is not in the base yet.
    job_id: int | None = None
    calls: list[LLMCall] = field(default_factory=list)


# Set per posting by record_job_run, read by record_call. A ContextVar and not
# a plain global because the transform stage runs postings on several threads at
# once, and each thread starts from its own empty context.
_CURRENT_CALLS: ContextVar[list[LLMCall] | None] = ContextVar(
    "current_calls", default=None
)

# Finished postings waiting to be written. Module level rather than per logger:
# the recording side has no logger to hand, and only one stage runs at a time.
_FINISHED_JOB_RUNS: "queue.Queue[JobRun]" = queue.Queue()


def record_call(call: LLMCall):
    """
    Attach a finished call to the posting being processed.

    A no-op outside a run, so calling a task straight from a script or a test
    still works and simply records nothing.

    Args:
        call (LLMCall): The call to record.
    """
    calls = _CURRENT_CALLS.get()
    if calls is None:
        return

    calls.append(call)

    return


@contextmanager
def record_job_run(source_file: str):
    """
    Record one posting, whatever happens to it.

    Runs on the worker thread. The exception is re-raised rather than swallowed:
    the caller still decides what a failed posting means for the batch, and this
    only makes sure the row exists either way.

    Args:
        source_file (str): Stem of the file being processed. Not a FactJob id,
            because at transform time the posting has not been loaded yet.

    Yields:
        JobRun: The record, already registered as the current posting.
    """
    job_run = JobRun(source_file=source_file, started_at=utc_now())
    token = _CURRENT_CALLS.set(job_run.calls)

    try:
        yield job_run
        job_run.status = "completed"
    except Exception as error:
        job_run.status = "failed"
        job_run.error = repr(error)
        raise
    finally:
        job_run.ended_at = utc_now()
        _CURRENT_CALLS.reset(token)
        # Queued before the exception leaves this frame, so by the time the
        # future resolves on the main thread the record is already waiting.
        _FINISHED_JOB_RUNS.put(job_run)


def _git_commit() -> str | None:
    """
    Short hash of the checked out commit, or None when git cannot say.

    Wrapped rather than trusted: git may be off the PATH, and a missing hash is
    no reason to lose the run.
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None

    return completed.stdout.strip() or None


def _config_snapshot() -> str:
    """
    The model settings this run used, as JSON for FactRun.config_json.

    MODEL_NAME is what was asked for and is usually empty; what the server
    actually served is recorded per call instead, where it is known.
    """
    return json.dumps(
        {
            "base_url": BASE_URL,
            "model_name": MODEL_NAME,
            "temperature": TEMPERATURE,
            "timeout": TIMEOUT,
        }
    )


class RunLogger:
    """
    Writes the run tables. Main thread only, one connection, one open run.

    Used as a context manager around a whole stage. The FactRun row is inserted
    and committed on the way in, so a run that is killed halfway stays visible
    as 'running' with a null ended_at instead of disappearing.
    """

    def __init__(
        self,
        stage: str,
        postings_total: int | None = None,
        max_concurrency: int | None = None,
    ):
        """
        Args:
            stage (str): 'extract', 'transform' or 'load', prefixed with the
                pipeline on the projects side ('projects_extract' and so on),
                since both write into the same FactRun table.
            postings_total (int | None): Files the stage found to work on.
            max_concurrency (int | None): Workers, or None when sequential.
        """
        self.stage = stage
        self.postings_total = postings_total
        self.max_concurrency = max_concurrency
        self.postings_ok = 0
        self.postings_failed = 0

        self.connection: sqlite3.Connection | None = None
        self.run_id: int | None = None

    def __enter__(self) -> "RunLogger":
        self.connection = sqlite3.connect(DB_PATH)
        self.connection.execute("PRAGMA foreign_keys = ON")

        cursor = self.connection.execute(
            """
            INSERT INTO FactRun (
                stage, started_at, status, postings_total, max_concurrency,
                config_json, git_commit
            )
            VALUES (?, ?, 'running', ?, ?, ?, ?)
            """,
            (
                self.stage,
                utc_now(),
                self.postings_total,
                self.max_concurrency,
                # Only the stage that calls the model. On extract these numbers
                # would be true and still misleading: nothing read them. Matched
                # by suffix so the projects pipeline's 'projects_transform'
                # counts too.
                _config_snapshot() if self.stage.endswith("transform") else None,
                _git_commit(),
            ),
        )
        self.run_id = cursor.lastrowid
        self.connection.commit()

        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.flush()

        self.connection.execute(
            """
            UPDATE FactRun
            SET ended_at = ?, status = ?, postings_total = ?, postings_ok = ?,
                postings_failed = ?, error = ?
            WHERE id = ?
            """,
            (
                utc_now(),
                "failed" if exc_type is not None else "completed",
                # Rewritten rather than left as inserted: a stage that only
                # learns its total once it starts working (the projects scan
                # walks a folder rather than a glob) sets it on the way out.
                self.postings_total,
                self.postings_ok,
                self.postings_failed,
                repr(exc_value) if exc_value is not None else None,
                self.run_id,
            ),
        )
        self.connection.commit()
        self.connection.close()

        # Never swallow: a stage that blew up still has to reach the caller.
        return False

    def flush(self):
        """
        Write every posting that has finished since the last call.

        Called from inside the transform loop as well as on the way out, since
        a batch runs for hours and a crash should not cost the rows of the
        postings that did finish.
        """
        while True:
            try:
                job_run = _FINISHED_JOB_RUNS.get_nowait()
            except queue.Empty:
                break

            self._insert_job_run(job_run)

        self.connection.commit()

    def _insert_job_run(self, job_run: JobRun):
        """
        Write one posting and its calls.

        Args:
            job_run (JobRun): A finished posting, drained off the queue.
        """
        cursor = self.connection.execute(
            """
            INSERT INTO FactJobRun (
                run_id, source_file, job_id, started_at, ended_at, status, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                job_run.source_file,
                job_run.job_id,
                job_run.started_at,
                job_run.ended_at,
                job_run.status,
                job_run.error,
            ),
        )
        job_run_id = cursor.lastrowid

        self.connection.executemany(
            """
            INSERT INTO FactLLMCall (
                job_run_id, task_name, attempt, started_at, ended_at,
                latency_ms, model_name, temperature, think, prompt_tokens,
                completion_tokens, prompt_sha1, http_status, status, error
            )
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    job_run_id,
                    call.task_name,
                    call.started_at,
                    call.ended_at,
                    call.latency_ms,
                    call.model_name,
                    call.temperature,
                    None if call.think is None else int(call.think),
                    call.prompt_tokens,
                    call.completion_tokens,
                    call.prompt_sha1,
                    call.http_status,
                    call.status,
                    call.error,
                )
                for call in job_run.calls
            ],
        )
