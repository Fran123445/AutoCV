
from pathlib import Path

import json

from etl.extract import JobDescriptionNotFound, extract_from_file


def main():
    data_dir = Path("data")
    staging_dir = data_dir / "staging"
    out_dir = data_dir / "extracted_descs"
    out_dir.mkdir(parents=True, exist_ok=True)

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


if __name__ == "__main__":
    main()