"""Durable stage outputs and archives for file-based ingestion queues."""

import hashlib
import json
import os
from pathlib import Path
import tempfile


SOURCE_HASH_KEY = "_autocv_source_sha256"


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: dict) -> None:
    """Publish complete JSON in one rename; failed writes leave no partial output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".autocv-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def archive_file(source: Path, directory: Path) -> Path:
    """Move a consumed input, preserving every prior archive on name collisions."""
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / source.name
    if destination.exists():
        digest = source_hash(source)[:12]
        destination = directory / f"{source.stem}.{digest}{source.suffix}"
        counter = 2
        while destination.exists():
            destination = directory / f"{source.stem}.{digest}.{counter}{source.suffix}"
            counter += 1
    source.rename(destination)
    return destination


def completed_output(source: Path, *directories: Path) -> Path | None:
    """Find a valid saved transformation of these exact input bytes."""
    digest = source_hash(source)
    original = json.loads(source.read_text(encoding="utf-8"))
    for directory in directories:
        if not directory.exists():
            continue
        for candidate in sorted(directory.iterdir()):
            if candidate.suffix != ".json" or not candidate.is_file():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if isinstance(data, dict) and data.get(SOURCE_HASH_KEY) == digest:
                return candidate
            # Older outputs predate fingerprints. They carry the complete
            # extracted posting, so compare that content, never just filenames.
            required = {"header", "body", "scrape_date", "technologies",
                        "concepts", "seniority", "role", "degree"}
            if (
                isinstance(data, dict) and SOURCE_HASH_KEY not in data
                and isinstance(original, dict)
                and {"header", "body", "scrape_date"} <= original.keys()
                and required <= data.keys()
                and all(data.get(key) == value for key, value in original.items())
            ):
                return candidate
    return None
