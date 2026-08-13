
from pathlib import Path

import json

from etl.extract import JobDescriptionNotFound, extract_from_file
# Aliased: this module has a transform() of its own, over directories rather
# than over a single posting.
from etl.transform import transform as transform_job

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


def transform(extract_output_dir: Path, transform_output_dir: Path):
    transformed_count = 0

    for json_path in sorted(extract_output_dir.glob("*.json")):
        print(f"Transforming {json_path}...")
        with json_path.open("r", encoding="utf-8") as f:
            extracted = json.load(f)

        transformed = transform_job(extracted)

        out_path = transform_output_dir / f"{json_path.stem}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(transformed, f, ensure_ascii=False, indent=2)
        transformed_count += 1

    print(f"\nTransformed {transformed_count}.")


def main():
    data_dir = Path("data")
    staging_dir = data_dir / "staging"
    out_dir = data_dir / "extracted_descs"
    out_dir.mkdir(parents=True, exist_ok=True)

    extract(staging_dir, out_dir)


if __name__ == "__main__":
    main()