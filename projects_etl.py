"""
Runs the personal projects pipeline: git repos in, Project rows out.

The mirror of jobs_etl.py, stage for stage, over a different source. What
differs is where the units come from. A posting is a file, so its stages glob a
directory; a project is a repo, so extract walks a parent folder and decides
which of its subdirectories are worth the model's time. From the JSON on disk
onwards the two pipelines are the same shape, which is why the transform and
load stages here read like their job side counterparts.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import argparse
import json

from config import PROJECTS_EXTRACT_DIR, PROJECTS_TRANSFORM_DIR
# Aliased, like the job side: this module has stage functions of its own whose
# names would otherwise shadow the imports.
from etl.projects.extract import extract as extract_projects
from etl.projects.load import load as load_project
from etl.projects.transform import transform as transform_project
from llm.config import MAX_CONCURRENCY
from run_log import RunLogger, record_job_run


def extract(parent_projects_dir: Path, out_dir: Path):
    """
    Scan a parent folder and write one signal file per surviving project.

    The scan is a single call over the whole folder rather than a loop the way
    the job side reads pages: which directories count as projects is decided by
    extract, not here. That also means a failure inside the scan takes the batch
    with it; the per-project records below cover the writes, so a project that
    made it into the gathered list still gets a row of its own.

    Args:
        parent_projects_dir (Path): Folder whose immediate subdirectories are
            the candidate projects.
        out_dir (Path): Where the signal JSON goes, one file per project.
    """
    extracted_count = 0
    failed = []

    with RunLogger("projects_extract") as run_log:
        print(f"Scanning {parent_projects_dir}...")
        gathered = extract_projects(str(parent_projects_dir))
        # Only known once the scan has run, unlike a glob the stage could count
        # up front. RunLogger writes it on the way out for exactly this case.
        run_log.postings_total = len(gathered)
        print(f"Kept {len(gathered)} projects.\n")

        for signals in gathered:
            print(f"Extracting {signals['name']}...")
            try:
                # Wrapped even though no model is involved, same as the job
                # side: the run tables are also where you look up which project
                # failed and when.
                with record_job_run(signals["name"]):
                    json_path = out_dir / f"{signals['name']}.json"
                    with json_path.open("w", encoding="utf-8") as f:
                        json.dump(signals, f, ensure_ascii=False, indent=2)
            except Exception as error:
                failed.append((signals["name"], error))
                print(f"  FAILED {signals['name']}: {error!r}")
                continue

            extracted_count += 1

        run_log.postings_ok = extracted_count
        run_log.postings_failed = len(failed)

    print(f"\nExtracted {extracted_count}, failed {len(failed)}.")
    for name, error in failed:
        print(f"  {name}: {error!r}")


def transform_one(json_path: Path, transform_output_dir: Path):
    """
    Transform a single extracted project and write it out.

    Runs on a worker thread. Every project reads and writes its own file, so the
    threads share nothing but the HTTP client, which is thread safe. The reads
    of the project's own source happen inside the sampler, and are reads only.

    Args:
        json_path (Path): The extract output to read.
        transform_output_dir (Path): Where the transformed project goes.
    """
    # Opens the project's telemetry record and closes it however this ends. The
    # model calls find it through a ContextVar, which is per thread, so the
    # worker running next door writes into its own record.
    with record_job_run(json_path.stem):
        with json_path.open("r", encoding="utf-8") as f:
            signals = json.load(f)

        transformed = transform_project(signals)

        out_path = transform_output_dir / f"{json_path.stem}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(transformed, f, ensure_ascii=False, indent=2)


def transform(extract_output_dir: Path, transform_output_dir: Path):
    json_paths = sorted(extract_output_dir.glob("*.json"))
    transformed_count = 0
    failed = []

    with RunLogger(
        "projects_transform",
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
            # that projects now report in completion order, not in filename
            # order. The telemetry rows are written here for the same reason:
            # sqlite takes one writer, and this thread is it.
            for future in as_completed(futures):
                json_path = futures[future]
                try:
                    future.result()
                except Exception as error:
                    # Deliberately broad. Three model passes per project, every
                    # one across the network, and one bad repo should not cost
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
                    # long should not lose the rows of the projects that did
                    # finish just because a later one killed the process.
                    run_log.flush()

        run_log.postings_ok = transformed_count
        run_log.postings_failed = len(failed)

    print(f"\nTransformed {transformed_count}, failed {len(failed)}.")
    for json_path, error in failed:
        print(f"  {json_path.name}: {error!r}")


def load(transform_output_dir: Path):
    """
    Load every transformed project into the database.

    Sequential, unlike transform: sqlite takes one writer, so there is no
    concurrency to gain here. The loader dedupes on the project's path, so one
    already in the base is skipped rather than failed, which is what lets this
    be re-run over the same directory.

    Args:
        transform_output_dir (Path): Where the transform stage wrote its JSON.
    """
    json_paths = sorted(transform_output_dir.glob("*.json"))
    loaded_count = 0
    skipped_count = 0
    failed = []

    with RunLogger("projects_load", postings_total=len(json_paths)) as run_log:
        for json_path in json_paths:
            try:
                # The same telemetry wrapper transform uses, so a load that
                # blows up on one project still leaves a FactJobRun row behind.
                # No model calls happen here, so its call list stays empty, and
                # job_id stays null: that column is a FactJob foreign key, and
                # a Project id would not point where it claims to.
                with record_job_run(json_path.stem):
                    with json_path.open("r", encoding="utf-8") as f:
                        transformed = json.load(f)

                    # RunLogger owns the one writer connection with foreign keys
                    # on; reuse it rather than open a second one that would only
                    # contend for the write lock.
                    project_id = load_project(transformed, run_log.connection)
            except Exception as error:
                failed.append((json_path, error))
                print(f"  FAILED {json_path.name}: {error!r}")
                continue

            if project_id is None:
                skipped_count += 1
                print(f"Skipped {json_path.name} (already loaded)")
            else:
                loaded_count += 1
                print(f"Loaded {json_path.name} [{loaded_count}/{len(json_paths)}]")

            # One project per flush, matching transform: a long batch should not
            # lose the telemetry of what did land if a later one kills it.
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
        description="Run the AutoCV personal projects ETL stages."
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
        "--projects-dir",
        type=Path,
        # No default: the repos live outside this project, and guessing at
        # somebody's code folder would either scan the wrong tree or nothing.
        help=(
            "Folder whose immediate subdirectories are the candidate projects. "
            "Required when the extract stage runs."
        ),
    )

    args = parser.parse_args()
    args.stages = args.stages or list(STAGES)

    if "extract" in args.stages and args.projects_dir is None:
        parser.error("--projects-dir is required when the extract stage runs")

    return args


def main():
    args = parse_args()
    stages = args.stages

    if "extract" in stages:
        PROJECTS_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
        extract(args.projects_dir, PROJECTS_EXTRACT_DIR)

    if "transform" in stages:
        PROJECTS_TRANSFORM_DIR.mkdir(parents=True, exist_ok=True)
        transform(PROJECTS_EXTRACT_DIR, PROJECTS_TRANSFORM_DIR)

    if "load" in stages:
        load(PROJECTS_TRANSFORM_DIR)


if __name__ == "__main__":
    main()
