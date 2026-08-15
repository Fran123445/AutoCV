
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import argparse
import json

from etl.extract import JobDescriptionNotFound, extract_from_file
# Aliased: this module has a transform() of its own, over directories rather
# than over a single posting.
from etl.transform import transform as transform_job
from llm.config import MAX_CONCURRENCY

def extract(staging_dir: Path, out_dir: Path):
    extracted_count = 0
    skipped = []

    for html_path in sorted(staging_dir.glob("*.html")):
        print(f"Extracting {html_path}...")
        try:
            extracted = extract_from_file(html_path)
        except JobDescriptionNotFound as error:
            # One page saved mid-render should not end the batch.
            skipped.append((html_path, error))
            continue

        json_path = out_dir / f"{html_path.stem}.json"
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)
        extracted_count += 1

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

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
        futures = {
            pool.submit(transform_one, json_path, transform_output_dir): json_path
            for json_path in json_paths
        }

        # Results are handled here on the main thread, so the counter needs no
        # lock and the progress lines do not interleave. The tradeoff is that
        # postings now report in completion order, not in filename order.
        for future in as_completed(futures):
            json_path = futures[future]
            try:
                future.result()
            except Exception as error:
                # Deliberately broad. This runs for hours, every call crosses
                # the network, and one bad posting should not cost the batch.
                failed.append((json_path, error))
                print(f"  FAILED {json_path.name}: {error!r}")
                continue

            transformed_count += 1
            print(f"Transformed {json_path.name} [{transformed_count}/{len(json_paths)}]")

    print(f"\nTransformed {transformed_count}, failed {len(failed)}.")
    for json_path, error in failed:
        print(f"  {json_path.name}: {error!r}")


STAGES = ("extract", "transform")


def parse_args():
    parser = argparse.ArgumentParser(description="Run the AutoCV ETL stages.")
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


if __name__ == "__main__":
    main()