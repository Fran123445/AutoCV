"""
Runs the job postings pipeline: scraped LinkedIn pages in, FactJob rows out.

The projects side has its own entry point, projects_etl.py, with the same three
stages over a different source. They stay separate scripts rather than one with
a switch: the two pipelines share nothing but the run tables, and a posting and
a repo have neither the same input nor the same idea of what a stage costs.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import argparse
import json

from config import (
    JOBS_EXTRACT_DIR,
    JOBS_EXTRACT_PROCESSED_DIR,
    JOBS_PROCESSED_DIR,
    JOBS_TRANSFORM_DIR,
    JOBS_TRANSFORM_PROCESSED_DIR,
    STAGING_DIR,
)
from etl.jobs.extract import JobDescriptionNotFound, extract_from_file
from etl.files import (
    SOURCE_HASH_KEY, archive_file, completed_output, source_hash, write_json,
)
from etl.jobs.load import load as load_job
# Aliased: this module has a transform() of its own, over directories rather
# than over a single posting.
from etl.jobs.transform import transform as transform_job
from llm.client import LLMClient
from llm.settings import LLMSettings
from run_log import RunLogger, record_item

def extract(
    staging_dir: Path,
    out_dir: Path,
    processed_dir: Path | None = None,
):
    processed_dir = processed_dir or JOBS_PROCESSED_DIR
    staging_dir.mkdir(parents=True, exist_ok=True)
    html_paths = sorted(
        path
        for path in staging_dir.iterdir()
        if path.is_file() and path.suffix.lower() in (".html", ".mhtml")
    )
    extracted_count = 0
    failed = []

    with RunLogger("jobs", "extract", items_total=len(html_paths)) as run_log:
        for html_path in html_paths:
            print(f"Extracting {html_path}...")
            try:
                # Wrapped even though no model is involved: the run tables are
                # also where you look up which page failed and when.
                with record_item(html_path.stem):
                    extracted = extract_from_file(html_path)

                    json_path = out_dir / f"{html_path.stem}.json"
                    # Never replace a different posting waiting for transform.
                    if json_path.exists():
                        existing = json.loads(json_path.read_text(encoding="utf-8"))
                        if existing != extracted:
                            raise FileExistsError(f"pending output already exists: {json_path}")
                    else:
                        write_json(json_path, extracted)
                    archive_file(html_path, processed_dir)
            except JobDescriptionNotFound as error:
                # One page saved mid-render should not end the batch.
                failed.append((html_path, error))
                continue
            except (OSError, ValueError) as error:
                # Keep files in staging when archiving fails, so the source is
                # still available for a retry and the failure is visible.
                failed.append((html_path, error))
                continue

            extracted_count += 1

        run_log.items_ok = extracted_count
        run_log.items_failed = len(failed)

    print(f"\nExtracted {extracted_count}, failed {len(failed)}.")
    for html_path, error in failed:
        print(f"  {html_path.name}: {error}")


def transform_one(
    json_path: Path,
    transform_output_dir: Path,
    llm_client: LLMClient,
    processed_dir: Path | None = None,
    processed_output_dir: Path | None = None,
    force: bool = False,
):
    """
    Transform a single extracted posting and write it out.

    Runs on a worker thread. Every posting reads and writes its own file, so
    the threads share nothing but the HTTP client, which is thread safe.

    Args:
        json_path (Path): The extract output to read.
        transform_output_dir (Path): Where the transformed posting goes.
    """
    # Opens the posting's telemetry record and closes it however this ends. The
    # model calls find it through a ContextVar, which is per thread, so the
    # worker running next door writes into its own record.
    with record_item(json_path.stem):
        processed_dir = processed_dir or JOBS_EXTRACT_PROCESSED_DIR
        processed_output_dir = processed_output_dir or JOBS_TRANSFORM_PROCESSED_DIR
        if not force and completed_output(
            json_path, transform_output_dir, processed_output_dir
        ):
            archive_file(json_path, processed_dir)
            return False

        with json_path.open("r", encoding="utf-8") as f:
            extracted = json.load(f)
        digest = source_hash(json_path)

        out_path = transform_output_dir / json_path.name
        if out_path.exists():
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if (
                existing.get(SOURCE_HASH_KEY) != digest
                and completed_output(json_path, transform_output_dir) != out_path
            ):
                raise FileExistsError(f"pending output already exists: {out_path}")

        transformed = transform_job(extracted, llm_client)
        if source_hash(json_path) != digest:
            raise RuntimeError(f"input changed during transformation: {json_path}")
        transformed[SOURCE_HASH_KEY] = digest
        write_json(out_path, transformed)
        archive_file(json_path, processed_dir)
        return True


def transform(
    extract_output_dir: Path,
    transform_output_dir: Path,
    llm_client: LLMClient,
    processed_dir: Path | None = None,
    processed_output_dir: Path | None = None,
    force: bool = False,
):
    concurrency = llm_client.settings.max_concurrency
    json_paths = sorted(extract_output_dir.glob("*.json"))
    transformed_count = 0
    recovered_count = 0
    failed = []

    with RunLogger(
        "jobs",
        "transform",
        items_total=len(json_paths),
        max_concurrency=concurrency,
        llm_settings=llm_client.settings,
    ) as run_log:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(
                    transform_one, json_path, transform_output_dir, llm_client,
                    processed_dir, processed_output_dir, force,
                ): json_path
                for json_path in json_paths
            }

            # Results are handled here on the main thread, so the counter needs
            # no lock and the progress lines do not interleave. The tradeoff is
            # that postings now report in completion order, not in filename
            # order. The telemetry rows are written here for the same reason:
            # sqlite takes one writer, and this thread is it.
            for future in as_completed(futures):
                json_path = futures[future]
                try:
                    was_transformed = future.result()
                except Exception as error:
                    # Deliberately broad. This runs for hours, every call
                    # crosses the network, and one bad posting should not cost
                    # the batch.
                    failed.append((json_path, error))
                    print(f"  FAILED {json_path.name}: {error!r}")
                    continue
                else:
                    if was_transformed:
                        transformed_count += 1
                        print(f"Transformed {json_path.name}")
                    else:
                        recovered_count += 1
                        print(f"Archived {json_path.name} (saved transformation reused)")
                finally:
                    # Every iteration rather than once at the end: a batch this
                    # long should not lose the rows of the postings that did
                    # finish just because a later one killed the process.
                    run_log.flush()

        run_log.items_ok = transformed_count + recovered_count
        run_log.items_failed = len(failed)

        print(
            f"\nTransformed {transformed_count}, recovered {recovered_count}, "
            f"failed {len(failed)}."
        )
        for json_path, error in failed:
            print(f"  {json_path.name}: {error!r}")


def load(transform_output_dir: Path, processed_dir: Path | None = None):
    """
    Load every transformed posting into the database.

    Sequential, unlike transform: sqlite takes one writer, so there is no
    concurrency to gain here. The loader dedupes on linkedin_job_id, so a
    posting already in the base is archived without touching applied status.
    Inputs move only after their database transaction is committed.

    Args:
        transform_output_dir (Path): Where the transform stage wrote its JSON.
    """
    processed_dir = processed_dir or JOBS_TRANSFORM_PROCESSED_DIR
    json_paths = sorted(transform_output_dir.glob("*.json"))
    loaded_count = 0
    skipped_count = 0
    failed = []

    with RunLogger("jobs", "load", items_total=len(json_paths)) as run_log:
        for json_path in json_paths:
            try:
                # The same telemetry wrapper transform uses, so a load that
                # blows up on one posting still leaves a FactRunItem row behind.
                # No model calls happen here, so its call list stays empty.
                with record_item(json_path.stem) as item:
                    with json_path.open("r", encoding="utf-8") as f:
                        transformed = json.load(f)

                    # RunLogger owns the one writer connection with foreign keys
                    # on; reuse it rather than open a second one that would only
                    # contend for the write lock.
                    job_id = load_job(transformed, run_log.connection)
                    item.produced("FactJob", job_id)
                    run_log.connection.commit()
                    archive_file(json_path, processed_dir)
            except Exception as error:
                failed.append((json_path, error))
                print(f"  FAILED {json_path.name}: {error!r}")
                continue

            if job_id is None:
                skipped_count += 1
                print(f"Archived {json_path.name} (already loaded)")
            else:
                loaded_count += 1
                print(f"Loaded {json_path.name} [{loaded_count}/{len(json_paths)}]")

            # One posting per flush, matching transform: a long batch should not
            # lose the telemetry of what did land if a later posting kills it.
            run_log.flush()

        run_log.items_ok = loaded_count + skipped_count
        run_log.items_failed = len(failed)

    print(
        f"\nLoaded {loaded_count}, already loaded {skipped_count}, failed {len(failed)}."
    )
    for json_path, error in failed:
        print(f"  {json_path.name}: {error!r}")


STAGES = ("extract", "transform", "load")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the AutoCV job postings ETL stages."
    )
    parser.add_argument(
        "stages",
        nargs="*",
        choices=STAGES,
        # Not a list of every stage: argparse validates a non-None default
        # against choices as a single value, and a list is not a choice. None
        # is the one default it skips, so the fallback happens below.
        default=None,
        help=(
            "Stages to run. Defaults to all of them. They always run in "
            "pipeline order, whatever order you list them in, since transform "
            "reads what extract wrote."
        ),
    )

    parser.add_argument(
        "--force", action="store_true",
        help="Transform pending extracted files again even if a saved result exists.",
    )
    args = parser.parse_args()
    args.stages = args.stages or list(STAGES)

    return args


def main():
    args = parse_args()
    stages = args.stages

    if "extract" in stages:
        JOBS_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
        extract(STAGING_DIR, JOBS_EXTRACT_DIR, JOBS_PROCESSED_DIR)

    if "transform" in stages:
        JOBS_TRANSFORM_DIR.mkdir(parents=True, exist_ok=True)
        settings = LLMSettings.from_env("jobs")
        with LLMClient(settings) as llm_client:
            transform(JOBS_EXTRACT_DIR, JOBS_TRANSFORM_DIR, llm_client, force=args.force)

    if "load" in stages:
        load(JOBS_TRANSFORM_DIR)


if __name__ == "__main__":
    main()
