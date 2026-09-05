from contextlib import contextmanager
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import experience_etl
import jobs_etl
from etl.files import SOURCE_HASH_KEY, archive_file, source_hash, write_json


@pytest.fixture
def stage_runtime(tmp_path, monkeypatch):
    """Real commit visibility, without needing the full application schema."""
    database = tmp_path / "stage.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE loaded (id TEXT PRIMARY KEY)")
    connection.commit()
    logger = SimpleNamespace(connection=connection, items_ok=0, items_failed=0)
    logger.flush = connection.commit

    @contextmanager
    def run_logger(*args, **kwargs):
        yield logger

    @contextmanager
    def item(*args):
        yield SimpleNamespace(produced=lambda *args: None)

    for module in (jobs_etl, experience_etl):
        monkeypatch.setattr(module, "RunLogger", run_logger)
        monkeypatch.setattr(module, "record_item", item)
    yield logger, database
    connection.close()


def test_transform_recovers_after_archive_failure_even_after_output_loaded(
    tmp_path, monkeypatch, stage_runtime,
):
    source = tmp_path / "pending/extracted/job.json"
    output = tmp_path / "pending/transformed"
    processed = tmp_path / "processed/extracted"
    loaded = tmp_path / "processed/transformed"
    write_json(source, {"body": "posting"})
    model = Mock(return_value={"body": "tagged posting"})
    monkeypatch.setattr(jobs_etl, "transform_job", model)
    monkeypatch.setattr(jobs_etl, "archive_file", Mock(side_effect=OSError("locked")))

    with pytest.raises(OSError, match="locked"):
        jobs_etl.transform_one(source, output, None, processed, loaded)
    assert source.exists()
    assert json.loads((output / source.name).read_text())[SOURCE_HASH_KEY] == source_hash(source)

    # Loading may run before retrying the failed archive operation.
    archive_file(output / source.name, loaded)
    monkeypatch.setattr(jobs_etl, "archive_file", archive_file)
    assert jobs_etl.transform_one(source, output, None, processed, loaded) is False
    assert model.call_count == 1
    assert not source.exists()
    assert (processed / source.name).exists()


def test_transform_failure_keeps_input_and_does_not_publish(
    tmp_path, monkeypatch, stage_runtime,
):
    source = tmp_path / "input/job.json"
    write_json(source, {"body": "posting"})
    monkeypatch.setattr(jobs_etl, "transform_job", Mock(side_effect=RuntimeError("model failed")))
    with pytest.raises(RuntimeError, match="model failed"):
        jobs_etl.transform_one(source, tmp_path / "out", None,
                               tmp_path / "done", tmp_path / "loaded")
    assert source.exists()
    assert not (tmp_path / "out/job.json").exists()


def test_changed_input_does_not_reuse_archived_result_and_force_reprocesses(
    tmp_path, monkeypatch, stage_runtime,
):
    source = tmp_path / "input/job.json"
    output, processed, loaded = [tmp_path / name for name in ("out", "done", "loaded")]
    model = Mock(return_value={"body": "tagged"})
    monkeypatch.setattr(jobs_etl, "transform_job", model)
    write_json(source, {"body": "original"})
    jobs_etl.transform_one(source, output, None, processed, loaded)
    archive_file(output / source.name, loaded)
    write_json(source, {"body": "changed"})
    jobs_etl.transform_one(source, output, None, processed, loaded)
    assert model.call_count == 2
    write_json(source, {"body": "changed"})
    jobs_etl.transform_one(source, output, None, processed, loaded, force=True)
    assert model.call_count == 3
    assert len(list(processed.glob("*.json"))) == 3


def test_failed_json_write_preserves_previous_output(tmp_path):
    target = tmp_path / "out.json"
    write_json(target, {"previous": True})
    with pytest.raises(TypeError):
        write_json(target, {"invalid": object()})
    assert json.loads(target.read_text()) == {"previous": True}
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("pipeline", ["jobs", "experience"])
def test_load_commits_before_archiving_and_retry_is_safe(
    tmp_path, monkeypatch, stage_runtime, pipeline,
):
    logger, database = stage_runtime
    module = jobs_etl if pipeline == "jobs" else experience_etl
    source = tmp_path / "pending/record.json"
    processed = tmp_path / "processed"
    write_json(source, {"id": "one"})

    def loader(data, connection):
        inserted = connection.execute("INSERT OR IGNORE INTO loaded VALUES (?)", (data["id"],)).rowcount
        if pipeline == "jobs":
            return 1 if inserted else None
        return dict(experiences_loaded=inserted, experiences_skipped=1-inserted,
                    projects_loaded=0, projects_skipped=0)

    monkeypatch.setattr(module, "load_job" if pipeline == "jobs" else "load_experience", loader)

    def interrupted_archive(path, directory):
        with sqlite3.connect(database) as reader:
            assert reader.execute("SELECT COUNT(*) FROM loaded").fetchone()[0] == 1
        raise OSError("archive locked")

    monkeypatch.setattr(module, "archive_file", interrupted_archive)

    def run():
        if pipeline == "jobs":
            module.load(source.parent, processed)
        else:
            module.load(source.parent, tmp_path / "record.toml", processed)

    if pipeline == "experience":
        with pytest.raises(OSError, match="archive locked"):
            run()
    else:
        run()
        assert logger.items_failed == 1
    assert source.exists()

    monkeypatch.setattr(module, "archive_file", archive_file)
    run()
    assert not source.exists()
    assert (processed / source.name).exists()
    assert logger.connection.execute("SELECT COUNT(*) FROM loaded").fetchone()[0] == 1
    run()  # An empty pending queue is a harmless no-op.


@pytest.mark.parametrize("pipeline", ["jobs", "experience"])
def test_failed_load_leaves_input_pending(tmp_path, monkeypatch, stage_runtime, pipeline):
    module = jobs_etl if pipeline == "jobs" else experience_etl
    source = tmp_path / "pending/record.json"
    write_json(source, {})
    loader = Mock(side_effect=ValueError("invalid data"))
    monkeypatch.setattr(module, "load_job" if pipeline == "jobs" else "load_experience", loader)
    if pipeline == "jobs":
        module.load(source.parent, tmp_path / "processed")
    else:
        with pytest.raises(ValueError, match="invalid data"):
            module.load(source.parent, tmp_path / "record.toml", tmp_path / "processed")
    assert source.exists()
    assert not (tmp_path / "processed").exists()
