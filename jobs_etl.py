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

from etl.jobs.extract import JobDescriptionNotFound, extract_from_file
from etl.jobs.load import load as load_job
# Aliased: this module has a transform() of its own, over directories rather
# than over a single posting.
from etl.jobs.transform import transform as transform_job
from llm.config import MAX_CONCURRENCY
from run_log import RunLogger, record_job_run

def extract(staging_dir: Path, out_dir: Path):
    html_paths = sorted(staging_dir.glob("*.html"))
    extracted_count = 0
    skipped = []

    with RunLogger("extract", postings_total=len(html_paths)) as run_log:
        for html_path in html_paths:
            print(f"Extracting {html_path}...")
            try:
                # Wrapped even though no model is involved: the run tables are
                # also where you look up which page failed and when.
                with record_job_run(html_path.stem):
                    extracted = extract_from_file(html_path)

                    json_path = out_dir / f"{html_path.stem}.json"
                    with json_path.open("w", encoding="utf-8") as f:
                        json.dump(extracted, f, ensure_ascii=False, indent=2)
            except JobDescriptionNotFound as error:
                # One page saved mid-render should not end the batch.
                skipped.append((html_path, error))
                continue

            extracted_count += 1

        run_log.postings_ok = extracted_count
        run_log.postings_failed = len(skipped)

    print(f"\nExtracted {extracted_count}, skipped {len(skipped)}.")
    for html_path, error in skipped:
        print(f"  {html_path.name}: {error}")


def transform_one(json_path: Path, transform_output_dir: Path):
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
    with record_job_run(json_path.stem):
        with json_path.open("r", encoding="utf-8") as f:
            extracted = json.load(f)

        transformed = transform_job(extracted)

        out_path = transform_output_dir / f"{json_path.stem}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(transformed, f, ensure_ascii=False, indent=2)


def transform(extract_output_dir: Path, transform_output_dir: Path):
    json_paths = sorted(extract_output_dir.glob("*.json"))
    transformed_count = 0
    failed = []

    with RunLogger(
        "transform",
        postings_total=len(json_paths),
        max_concurrency=MAX_CONCURRENCY,
    ) as run_log:
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            futures = {
                pool.submit(transform_one, json_path, transform_output_dir): json_path
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
                    future.result()
                except Exception as error:
                    # Deliberately broad. This runs for hours, every call
                    # crosses the network, and one bad posting should not cost
                    # the batch.
                    failed.append((json_path, error))
                    print(f"  FAILED {json_path.name}: {error!r}")
                    continue
                else:
                    transformed_count += 1
                    print(
                        f"Transformed {json_path.name} "
                        f"[{transformed_count}/{len(json_paths)}]"
                    )
                finally:
                    # Every iteration rather than once at the end: a batch this
                    # long should not lose the rows of the postings that did
                    # finish just because a later one killed the process.
                    run_log.flush()

        run_log.postings_ok = transformed_count
        run_log.postings_failed = len(failed)

    print(f"\nTransformed {transformed_count}, failed {len(failed)}.")
    for json_path, error in failed:
        print(f"  {json_path.name}: {error!r}")


def load(transform_output_dir: Path):
    """
    Load every transformed posting into the database.

    Sequential, unlike transform: sqlite takes one writer, so there is no
    concurrency to gain here. The loader dedupes on linkedin_job_id, so a
    posting already in the base is skipped rather than failed, which is what
    lets this be re-run over the same directory without touching applied status.

    Args:
        transform_output_dir (Path): Where the transform stage wrote its JSON.
    """
    json_paths = sorted(transform_output_dir.glob("*.json"))
    loaded_count = 0
    skipped_count = 0
    failed = []

    with RunLogger("load", postings_total=len(json_paths)) as run_log:
        for json_path in json_paths:
            try:
                # The same telemetry wrapper transform uses, so a load that
                # blows up on one posting still leaves a FactJobRun row behind.
                # No model calls happen here, so its call list stays empty.
                with record_job_run(json_path.stem) as job_run:
                    with json_path.open("r", encoding="utf-8") as f:
                        transformed = json.load(f)

                    # RunLogger owns the one writer connection with foreign keys
                    # on; reuse it rather than open a second one that would only
                    # contend for the write lock.
                    job_id = load_job(transformed, run_log.connection)
                    job_run.job_id = job_id
            except Exception as error:
                failed.append((json_path, error))
                print(f"  FAILED {json_path.name}: {error!r}")
                continue

            if job_id is None:
                skipped_count += 1
                print(f"Skipped {json_path.name} (already loaded)")
            else:
                loaded_count += 1
                print(f"Loaded {json_path.name} [{loaded_count}/{len(json_paths)}]")

            # One posting per flush, matching transform: a long batch should not
            # lose the telemetry of what did land if a later posting kills it.
            run_log.flush()

        run_log.postings_ok = loaded_count
        run_log.postings_failed = len(failed)

    print(
        f"\nLoaded {loaded_count}, skipped {skipped_count}, failed {len(failed)}."
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

    args = parser.parse_args()
    args.stages = args.stages or list(STAGES)

    return args


def main():
    args = parse_args()
    stages = args.stages

    data_dir = Path("data")
    staging_dir = data_dir / "staging"
    extract_output_dir = data_dir / "extracted_descs"
    transform_output_dir = data_dir / "transformed_descs"

    if "extract" in stages:
        extract_output_dir.mkdir(parents=True, exist_ok=True)
        extract(staging_dir, extract_output_dir)

    if "transform" in stages:
        transform_output_dir.mkdir(parents=True, exist_ok=True)
        transform(extract_output_dir, transform_output_dir)

    if "load" in stages:
        load(transform_output_dir)


if __name__ == "__main__":
    main()