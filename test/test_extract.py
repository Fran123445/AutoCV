import os

from datetime import datetime, timezone

import pytest

from etl.jobs.config import BODY_START_ANCHOR
from etl.jobs.extract import (
    JobDescriptionNotFound,
    UnsupportedJobSource,
    extract_from_file,
    read_saved_page,
)


SOURCE_URL = "https://www.linkedin.com/jobs/view/4231234567/"


def make_page(body="Buscamos un ingeniero de datos. " * 20):
    return (
        f"<!-- saved from url=(0045){SOURCE_URL} -->"
        "<html><head><title>Data Engineer | Acme | LinkedIn</title></head>"
        "<body><p>Data Engineer Acme • Buenos Aires · hace 3 meses</p>"
        f"<p>{BODY_START_ANCHOR}</p><p>{body}</p></body></html>"
    )


def make_mhtml(html=None, snapshot_url=SOURCE_URL, with_html_part=True):
    html = html or make_page()
    header = (
        "From: <Saved by Blink>\r\n"
        f"Snapshot-Content-Location: {snapshot_url}\r\n"
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/related; boundary="----BOUND"\r\n\r\n'
    )
    html_part = (
        "------BOUND\r\nContent-Type: text/html\r\n"
        "Content-Transfer-Encoding: 8bit\r\n\r\n"
        f"{html}\r\n"
    )
    image_part = (
        "------BOUND\r\nContent-Type: image/png\r\n"
        "Content-Transfer-Encoding: base64\r\n\r\n"
        "iVBORw0KGgo=\r\n"
    )
    parts = [header]
    if with_html_part:
        parts.append(html_part)
    parts.extend([image_part, "------BOUND--\r\n"])
    return "".join(parts).encode("utf-8")


def test_read_saved_page_reads_source_url_from_html(tmp_path):
    path = tmp_path / "posting.html"
    path.write_text("<!-- saved from url=(0045)" + SOURCE_URL + " -->", encoding="utf-8")
    _, source = read_saved_page(path)
    assert source == {"source_url": SOURCE_URL}


def test_read_saved_page_ignores_source_comments_after_4000_chars(tmp_path):
    path = tmp_path / "posting.html"
    path.write_text(
        "x" * 4100 + "<!-- saved from url=(0045)" + SOURCE_URL + " -->",
        encoding="utf-8",
    )
    _, source = read_saved_page(path)
    assert source == {"source_url": None}


def test_read_saved_page_reads_the_first_html_part_from_mhtml(tmp_path):
    path = tmp_path / "posting.mhtml"
    path.write_bytes(make_mhtml())
    html, source = read_saved_page(path)
    assert html.startswith("<!-- saved from url")
    assert source == {"source_url": SOURCE_URL}


def test_read_saved_page_without_html_part_raises(tmp_path):
    path = tmp_path / "imageonly.mhtml"
    path.write_bytes(make_mhtml(with_html_part=False))
    with pytest.raises(JobDescriptionNotFound):
        read_saved_page(path)


def test_extract_from_file_dispatches_linkedin_for_mhtml(tmp_path):
    path = tmp_path / "posting.mhtml"
    path.write_bytes(make_mhtml())
    result = extract_from_file(path)
    assert result["header"]["linkedin_job_id"] == 4231234567


def test_extract_from_file_stamps_scrape_date(tmp_path):
    path = tmp_path / "posting.html"
    path.write_text(make_page(), encoding="utf-8")
    when = datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc).timestamp()
    os.utime(path, (when, when))
    assert extract_from_file(path)["scrape_date"] == "2026-03-14"


def test_extract_from_file_rejects_unknown_source(tmp_path):
    path = tmp_path / "posting.html"
    path.write_text(
        "<!-- saved from url=(0028)https://example.com/job/1 -->",
        encoding="utf-8",
    )
    with pytest.raises(UnsupportedJobSource):
        extract_from_file(path)
