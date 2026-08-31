from contextlib import contextmanager
import json

import jobs_etl
from etl.jobs.extract import JobDescriptionNotFound


class DummyRunLogger:
    def __init__(self, *_args, **_kwargs):
        self.items_ok = 0
        self.items_failed = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


@contextmanager
def dummy_record_item(_item_name):
    yield


def test_extract_moves_successful_source_to_processed_dir(tmp_path, monkeypatch):
    staging_dir = tmp_path / "staging"
    extract_dir = tmp_path / "extracted"
    processed_dir = tmp_path / "processed"
    staging_dir.mkdir()
    extract_dir.mkdir()

    source_path = staging_dir / "Data Engineer _ LinkedIn.mhtml"
    source_path.write_text("saved page", encoding="utf-8")

    monkeypatch.setattr(jobs_etl, "RunLogger", DummyRunLogger)
    monkeypatch.setattr(jobs_etl, "record_item", dummy_record_item)
    monkeypatch.setattr(
        jobs_etl,
        "extract_from_file",
        lambda _path: {"header": {}, "body": "description"},
    )

    jobs_etl.extract(staging_dir, extract_dir, processed_dir)

    assert not source_path.exists()
    assert (processed_dir / source_path.name).read_text(encoding="utf-8") == "saved page"
    with (extract_dir / "Data Engineer _ LinkedIn.json").open(encoding="utf-8") as f:
        assert json.load(f)["body"] == "description"


def test_extract_leaves_failed_source_in_staging(tmp_path, monkeypatch):
    staging_dir = tmp_path / "staging"
    extract_dir = tmp_path / "extracted"
    processed_dir = tmp_path / "processed"
    staging_dir.mkdir()
    extract_dir.mkdir()

    source_path = staging_dir / "incomplete.html"
    source_path.write_text("partial page", encoding="utf-8")

    monkeypatch.setattr(jobs_etl, "RunLogger", DummyRunLogger)
    monkeypatch.setattr(jobs_etl, "record_item", dummy_record_item)

    def fail_extract(_path):
        raise JobDescriptionNotFound("missing description")

    monkeypatch.setattr(jobs_etl, "extract_from_file", fail_extract)

    jobs_etl.extract(staging_dir, extract_dir, processed_dir)

    assert source_path.exists()
    assert not processed_dir.exists()
