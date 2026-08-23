"""
Runs the experience pipeline: one hand-written TOML file in, the rows the CV is
written from out.

The third entry point beside jobs_etl.py and projects_etl.py, and the odd one of
the three: the source is a single file the candidate fills in by hand, so there
is no batch here. Nothing is globbed, and a failure is the run rather than one
unit of it, which is why the stages below re-raise instead of collecting a
failure list.
"""

from pathlib import Path

import argparse
import json

from config import EXPERIENCE_PATH, EXPERIENCE_TRANSFORM_DIR
from etl.experience.extract import extract as extract_experience
from etl.experience.load import load as load_experience
from etl.experience.transform import transform as transform_experience
from run_log import RunLogger, record_item


def extract(experience_path: Path):
    """
    Read and validate the experience file.

    Writes nothing, unlike the other two extracts: the file is already the
    structured artifact, and an extract folder would hold a copy of the source
    and nothing else. What the stage is for is the validation — a misspelled key
    or a duplicate id costs a TOML parse to find here and a full run of model
    calls to find in transform, which reads the source again for the same reason.

    Args:
        experience_path (Path): The filled template, normally
            config.EXPERIENCE_PATH.
    """
    with RunLogger("experience", "extract", items_total=1) as run_log:
        print(f"Extracting {experience_path}...")
        try:
            # Wrapped even though no model is involved, same as the other two
            # pipelines: the run tables are also where you look up when the file
            # last parsed and what it said when it did not.
            with record_item(experience_path.stem):
                experience = extract_experience(experience_path)
        except Exception:
            run_log.items_failed = 1
            raise

        run_log.items_ok = 1

    projects_count = sum(len(job.project) for job in experience.job)
    print(
        f"\nRead {len(experience.job)} jobs, {projects_count} projects, "
        f"{len(experience.education)} education blocks."
    )


def transform(experience_path: Path, transform_output_dir: Path):
    """
    Transform the experience file and write it out.

    Single threaded, unlike the other two transform stages: there is one unit,
    and the model passes inside it run job by job. There is nothing for a pool to
    spread, so the run is logged with no max_concurrency.

    The source is read here rather than handed over from the extract stage, since
    that stage leaves nothing on disk. Running transform alone is therefore a
    complete run, and running extract first only buys the validation earlier.

    Args:
        experience_path (Path): The filled template, normally
            config.EXPERIENCE_PATH.
        transform_output_dir (Path): Where the transformed experience goes.
    """
    with RunLogger("experience", "transform", items_total=1) as run_log:
        print(f"Transforming {experience_path}...")
        try:
            with record_item(experience_path.stem):
                experience = extract_experience(experience_path)
                transformed = transform_experience(experience)

                out_path = transform_output_dir / f"{experience_path.stem}.json"
                with out_path.open("w", encoding="utf-8") as f:
                    json.dump(transformed, f, ensure_ascii=False, indent=2)
        except Exception:
            run_log.items_failed = 1
            raise

        run_log.items_ok = 1

    print(f"\nTransformed {experience_path.name} into {out_path}.")


def load(transform_output_dir: Path, experience_path: Path):
    """
    Load the transformed experience into the database.

    Nothing to flush between units and nothing to skip past, unlike the other two
    load stages: the loader takes the file whole. Jobs and projects are still
    deduped one by one inside it, which is what lets this be re-run over a file
    that grew a block since last time.

    Args:
        transform_output_dir (Path): Where the transform stage wrote its JSON.
        experience_path (Path): The source file, read only for its stem, which
            is the name both other stages logged their rows under.
    """
    json_path = transform_output_dir / f"{experience_path.stem}.json"

    with RunLogger("experience", "load", items_total=1) as run_log:
        print(f"Loading {json_path}...")
        try:
            # The same telemetry wrapper the other stages use. No model calls
            # happen here, so its call list stays empty, and the entity columns
            # stay null: the unit here is the whole file, and the loader writes
            # many rows out of it rather than the one those columns name.
            with record_item(json_path.stem):
                with json_path.open("r", encoding="utf-8") as f:
                    transformed = json.load(f)

                # RunLogger owns the one writer connection with foreign keys on;
                # reuse it rather than open a second one that would only contend
                # for the write lock.
                counts = load_experience(transformed, run_log.connection)
        except Exception:
            run_log.items_failed = 1
            raise

        run_log.items_ok = 1

    print(
        f"\nLoaded {counts['experiences_loaded']} jobs and "
        f"{counts['projects_loaded']} projects, skipped "
        f"{counts['experiences_skipped']} jobs and "
        f"{counts['projects_skipped']} projects already in the base."
    )


STAGES = ("extract", "transform", "load")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the AutoCV experience ETL stages."
    )
    parser.add_argument(
        "stages",
        nargs="*",
        choices=STAGES,
        default=None,
        help=(
            "Stages to run. Defaults to all of them. They always run in "
            "pipeline order, whatever order you list them in."
        ),
    )
    parser.add_argument(
        "--experience-path",
        type=Path,
        default=EXPERIENCE_PATH,
        help="The filled experience template to read.",
    )

    args = parser.parse_args()
    args.stages = args.stages or list(STAGES)

    return args


def main():
    args = parse_args()
    stages = args.stages

    if "extract" in stages:
        extract(args.experience_path)

    if "transform" in stages:
        EXPERIENCE_TRANSFORM_DIR.mkdir(parents=True, exist_ok=True)
        transform(args.experience_path, EXPERIENCE_TRANSFORM_DIR)

    if "load" in stages:
        load(EXPERIENCE_TRANSFORM_DIR, args.experience_path)


if __name__ == "__main__":
    main()
