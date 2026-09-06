"""
Run telemetry: what a stage did, item by item and call by call.

Two halves that never touch the same objects. The recording half is what the
worker threads use: a ContextVar holding the current item's call list, so
llm.client can log a call without every task having to pass a run id down.
The writing half is RunLogger, which owns the only connection and runs on the
main thread. Finished items cross between the two on a queue, because sqlite
takes one writer and the transform stage has MAX_CONCURRENCY of them.

'Item' is whatever the pipeline's unit of work is: a posting on the jobs side,
a repo on the projects side, the whole file on the experience side, one resume
on the resume side.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import hashlib
import json
import queue
import sqlite3

from config import DB_PATH, ROOT_DIR
from gitcli import head_commit
from llm.settings import LLMSettings
from app_log import configure_run_logging, get_logger


logger = get_logger(__name__)


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
    reasoning_effort: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_sha1: str | None = None
    http_status: int | None = None
    status: str = "running"
    error: str | None = None


@dataclass
class RunItem:
    """One unit of work inside one run, with the calls it made. A FactRunItem row."""

    item_key: str
    started_at: str
    ended_at: str | None = None
    status: str = "running"
    error: str | None = None
    # Which row this unit is about, named rather than referenced: the parent
    # table differs per pipeline. Both stay null on a stage that produces no
    # single row, which is most of them.
    entity_table: str | None = None
    entity_id: int | None = None
    calls: list[LLMCall] = field(default_factory=list)

    def produced(self, entity_table: str, entity_id: int | None):
        """
        Point this unit at the row it wrote.

        One call rather than two assignments, so a stage cannot set the table,
        forget the id, and leave a row claiming to be about nothing.

        Args:
            entity_table (str): Table the id belongs to, 'FactJob' and so on.
            entity_id (int | None): The row. None when the loader deduped and
                wrote nothing, which leaves the pair null as if never set.
        """
        if entity_id is None:
            return

        self.entity_table = entity_table
        self.entity_id = entity_id

        return


# Set per item by record_item, read by record_call. A ContextVar and not a
# plain global because the transform stage runs items on several threads at
# once, and each thread starts from its own empty context.
_CURRENT_CALLS: ContextVar[list[LLMCall] | None] = ContextVar(
    "current_calls", default=None
)

# Finished items waiting to be written. Module level rather than per logger:
# the recording side has no logger to hand, and only one stage runs at a time.
_FINISHED_ITEMS: "queue.Queue[RunItem]" = queue.Queue()


def record_call(call: LLMCall):
    """
    Attach a finished call to the item being processed.

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
def record_item(item_key: str):
    """
    Record one unit of work, whatever happens to it.

    Runs on the worker thread. The exception is re-raised rather than swallowed:
    the caller still decides what a failed item means for the batch, and this
    only makes sure the row exists either way.

    Args:
        item_key (str): Names the unit. Not a database id, because at transform
            time nothing the stage handles has been loaded yet.

    Yields:
        RunItem: The record, already registered as the current item.
    """
    item = RunItem(item_key=item_key, started_at=utc_now())
    logger.debug("Started stage item: %s", item_key)
    token = _CURRENT_CALLS.set(item.calls)

    try:
        yield item
        item.status = "completed"
    except Exception as error:
        item.status = "failed"
        item.error = repr(error)
        raise
    finally:
        item.ended_at = utc_now()
        _CURRENT_CALLS.reset(token)
        logger.debug(
            "Finished stage item: item=%s status=%s calls=%s",
            item.item_key,
            item.status,
            len(item.calls),
        )
        # Queued before the exception leaves this frame, so by the time the
        # future resolves on the main thread the record is already waiting.
        _FINISHED_ITEMS.put(item)


def _config_snapshot(settings: LLMSettings | None = None) -> str:
    """
    The model settings this run used, as JSON for FactRun.config_json.

    The selected model is what was asked for and is usually empty when a local
    server chooses its own model; what the server actually served is recorded
    per call instead, where it is known.
    """
    return json.dumps(
        settings.snapshot() if settings is not None else {}
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
        pipeline: str,
        stage: str,
        items_total: int | None = None,
        max_concurrency: int | None = None,
        llm_settings: LLMSettings | None = None,
    ):
        """
        Args:
            pipeline (str): 'jobs', 'projects', 'experience' or 'resume'. Its
                own argument because all four write the same FactRun table and
                the stage names repeat across them.
            stage (str): 'extract', 'transform' or 'load', and 'write',
                'render' or 'pdf' on the resume side.
            items_total (int | None): Units the stage found to work on.
            max_concurrency (int | None): Workers, or None when sequential.
            llm_settings: Settings used by the stage's LLM client, when it has
                one. Used to make the run configuration auditable.
        """
        self.pipeline = pipeline
        self.stage = stage
        self.items_total = items_total
        self.max_concurrency = max_concurrency
        self.llm_settings = llm_settings
        self.items_ok = 0
        self.items_failed = 0

        self.connection: sqlite3.Connection | None = None
        self.run_id: int | None = None
        self.log_path: Path | None = None

    def __enter__(self) -> "RunLogger":
        self.connection = sqlite3.connect(DB_PATH)
        self.connection.execute("PRAGMA foreign_keys = ON")

        cursor = self.connection.execute(
            """
            INSERT INTO FactRun (
                pipeline, stage, started_at, status, items_total,
                max_concurrency, config_json, git_commit
            )
            VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
            """,
            (
                self.pipeline,
                self.stage,
                utc_now(),
                self.items_total,
                self.max_concurrency,
                # Every run, not only the ones that reach the model. Non-LLM
                # stages carry an empty configuration snapshot.
                _config_snapshot(self.llm_settings),
                head_commit(ROOT_DIR, short=True),
            ),
        )
        self.run_id = cursor.lastrowid
        self.connection.commit()
        self.log_path = configure_run_logging(self.pipeline, self.run_id)

        logger.info(
            "Starting %s/%s stage (run_id=%s, items_total=%s, max_concurrency=%s, log=%s)",
            self.pipeline,
            self.stage,
            self.run_id,
            self.items_total,
            self.max_concurrency,
            self.log_path,
        )

        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.flush()

        self.connection.execute(
            """
            UPDATE FactRun
            SET ended_at = ?, status = ?, items_total = ?, items_ok = ?,
                items_failed = ?, error = ?
            WHERE id = ?
            """,
            (
                utc_now(),
                "failed" if exc_type is not None else "completed",
                # Rewritten rather than left as inserted: a stage that only
                # learns its total once it starts working (the projects scan
                # walks a folder rather than a glob) sets it on the way out.
                self.items_total,
                self.items_ok,
                self.items_failed,
                repr(exc_value) if exc_value is not None else None,
                self.run_id,
            ),
        )
        self.connection.commit()
        self.connection.close()

        logger.info(
            "Finished %s/%s stage: status=%s items_ok=%s items_failed=%s",
            self.pipeline,
            self.stage,
            "failed" if exc_type is not None else "completed",
            self.items_ok,
            self.items_failed,
        )
        if exc_type is not None:
            logger.error(
                "Stage raised an exception: %s/%s error=%s",
                self.pipeline,
                self.stage,
                exc_value,
                exc_info=(exc_type, exc_value, traceback),
            )

        # Never swallow: a stage that blew up still has to reach the caller.
        return False

    def flush(self):
        """
        Write every item that has finished since the last call.

        Called from inside the transform loop as well as on the way out, since
        a batch runs for hours and a crash should not cost the rows of the
        items that did finish.
        """
        while True:
            try:
                item = _FINISHED_ITEMS.get_nowait()
            except queue.Empty:
                break

            self._insert_item(item)

            if item.status == "failed":
                logger.error(
                    "Stage item failed: item=%s error=%s",
                    item.item_key,
                    item.error,
                )

        self.connection.commit()

    def _insert_item(self, item: RunItem):
        """
        Write one unit of work and its calls.

        Args:
            item (RunItem): A finished unit, drained off the queue.
        """
        cursor = self.connection.execute(
            """
            INSERT INTO FactRunItem (
                run_id, item_key, entity_table, entity_id, started_at,
                ended_at, status, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                item.item_key,
                item.entity_table,
                item.entity_id,
                item.started_at,
                item.ended_at,
                item.status,
                item.error,
            ),
        )
        run_item_id = cursor.lastrowid

        self.connection.executemany(
            """
            INSERT INTO FactLLMCall (
                run_item_id, task_name, attempt, started_at, ended_at,
                latency_ms, model_name, temperature, reasoning_effort,
                prompt_tokens, completion_tokens, prompt_sha1, http_status,
                status, error
            )
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_item_id,
                    call.task_name,
                    call.started_at,
                    call.ended_at,
                    call.latency_ms,
                    call.model_name,
                    call.temperature,
                    call.reasoning_effort,
                    call.prompt_tokens,
                    call.completion_tokens,
                    call.prompt_sha1,
                    call.http_status,
                    call.status,
                    call.error,
                )
                for call in item.calls
            ],
        )
