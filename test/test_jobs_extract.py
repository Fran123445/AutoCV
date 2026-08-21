import os

from datetime import datetime, timezone

import pytest

from etl.jobs.config import (
    BODY_END_ANCHORS,
    BODY_START_ANCHOR,
    CONTRACT_TYPES,
    MIN_BODY_LENGTH,
    MODALITIES,
)
from etl.jobs.extract import (
    JobDescriptionNotFound,
    _clean_html,
    _extract_body,
    _extract_company,
    _extract_location,
    _extract_posted,
    _extract_source,
    _longest_common_suffix,
    _read_mhtml,
    extract_from_file,
    extract_from_html,
)


def make_page(
    title="Data Engineer | Acme",
    subheader=(
        f"Data Engineer Acme • Buenos Aires · hace 3 meses "
        f"· {MODALITIES[0]} · {CONTRACT_TYPES[0]}"
    ),
    body="Buscamos un ingeniero de datos. " * 20,
    end_anchor=BODY_END_ANCHORS[0],
    source_url="https://www.linkedin.com/jobs/view/4231234567/",
):
    """
    Minimal saved-page markup carrying the anchors extract.py looks for.

    Every LinkedIn UI string comes from etl/jobs/config.py rather than being
    retyped, so these tests cover the parse structure and never the wording.
    A LinkedIn rewording is a config edit and leaves the suite untouched; it
    is caught at runtime by extract_from_html raising, not by any test here.
    """
    return (
        f"<!-- saved from url=(0045){source_url} -->"
        f"<html><head><title>{title} | LinkedIn</title>"
        f"<style>body {{ color: red; }}</style></head>"
        f"<body><p>{subheader}</p>"
        f"<p>{BODY_START_ANCHOR}</p><p>{body}</p>"
        f"<p>{end_anchor}</p><p>rail junk from another posting</p></body></html>"
    )


# --------------------------------------------------------------------------
# _clean_html
# --------------------------------------------------------------------------

@pytest.mark.parametrize("html, expected", [
    ("<p>Hello world</p>", "Hello world"),
    # Runs of whitespace collapse to one space.
    ("<p>Hello     world</p>", "Hello world"),
    # Separate tags are joined by a space rather than run together.
    ("<p>Hello</p><p>world</p>", "Hello world"),
    # The three tags decompose() drops carry no readable text.
    ("<script>var x = 1;</script><p>Hello</p>", "Hello"),
    ("<style>p { color: red; }</style><p>Hello</p>", "Hello"),
    ("<noscript>enable js</noscript><p>Hello</p>", "Hello"),
    # Leading and trailing whitespace is stripped.
    ("<p>   Hello   </p>", "Hello"),
], ids=[
    "plain",
    "collapses_runs",
    "joins_tags",
    "drops_script",
    "drops_style",
    "drops_noscript",
    "strips_edges",
])
def test_clean_html(html, expected):
    assert _clean_html(html) == expected


# --------------------------------------------------------------------------
# _extract_source
# --------------------------------------------------------------------------

def test_source_reads_url_and_job_id():
    html = "<!-- saved from url=(0045)https://www.linkedin.com/jobs/view/4231234567/ -->"
    assert _extract_source(html) == {
        "source_url": "https://www.linkedin.com/jobs/view/4231234567/",
        "linkedin_job_id": 4231234567,
    }


def test_source_without_save_comment_is_all_none():
    assert _extract_source("<html><body>no comment here</body></html>") == {
        "source_url": None,
        "linkedin_job_id": None,
    }


def test_source_url_without_job_id_keeps_the_url():
    html = "<!-- saved from url=(0032)https://www.linkedin.com/feed/ -->"
    result = _extract_source(html)

    assert result["source_url"] == "https://www.linkedin.com/feed/"
    assert result["linkedin_job_id"] is None


def test_source_ignores_ids_past_the_first_4000_characters():
    """
    The search window is deliberate: the recommended-jobs rail further down the
    page carries ids of unrelated postings, and one of those must never win.
    """
    html = (
        "x" * 4100
        + "<!-- saved from url=(0045)https://www.linkedin.com/jobs/view/999/ -->"
    )

    assert _extract_source(html) == {"source_url": None, "linkedin_job_id": None}


# --------------------------------------------------------------------------
# _extract_posted
# --------------------------------------------------------------------------

@pytest.mark.parametrize("header, expected_days", [
    ("· hace 30 minutos", 0),
    ("· hace 5 horas", 0),
    ("· hace 1 día", 1),
    ("· hace 4 días", 4),
    ("· hace 2 semanas", 14),
    ("· hace 1 mes", 30),
    ("· hace 3 meses", 90),
    ("· hace 1 año", 365),
    ("· hace 2 años", 730),
    # "más de" is optional in the pattern and must not change the number read.
    ("· hace más de 1 año", 365),
], ids=[
    "minutes", "hours", "one_day", "days", "weeks",
    "one_month", "months", "one_year", "years", "mas_de",
])
def test_posted_days_ago(header, expected_days):
    assert _extract_posted(header)["posted_days_ago"] == expected_days


def test_posted_keeps_the_raw_phrase():
    assert _extract_posted("Acme · hace más de 1 año")["posted_raw"] == "hace más de 1 año"


def test_posted_absent_is_all_none():
    assert _extract_posted("Acme • Buenos Aires") == {
        "posted_raw": None,
        "posted_days_ago": None,
    }


# --------------------------------------------------------------------------
# _longest_common_suffix
# --------------------------------------------------------------------------

@pytest.mark.parametrize("left, right, expected", [
    ("Acme Corp", "hello Acme Corp", "Acme Corp"),
    ("Data | Acme", "Buenos Acme", " Acme"),
    ("abc", "xyz", ""),
    ("", "abc", ""),
    ("abc", "", ""),
    # Identical strings share all of themselves.
    ("Acme", "Acme", "Acme"),
], ids=["full_left", "partial", "nothing", "empty_left", "empty_right", "identical"])
def test_longest_common_suffix(left, right, expected):
    assert _longest_common_suffix(left, right) == expected


# --------------------------------------------------------------------------
# _extract_company
# --------------------------------------------------------------------------

@pytest.mark.parametrize("header, full_title, expected", [
    # Straight case: the subheader confirms where the title splits.
    ("Data Engineer Acme • Buenos Aires", "Data Engineer | Acme", "Acme"),
    # The company itself contains a pipe. Splitting the title on the last pipe
    # would return "Corp"; the subheader is what recovers the whole name.
    ("Data Engineer Acme | Corp • Buenos Aires", "Data | Eng | Acme | Corp", "Acme | Corp"),
    # No bullet means no subheader to confirm against, so it falls back to
    # everything after the last pipe in the title.
    ("Data Engineer, no bullet anywhere", "Data Engineer | Acme", "Acme"),
    # Bullet present but sharing nothing with the title: same fallback.
    ("Totally unrelated • Buenos Aires", "Data Engineer | Acme", "Acme"),
], ids=["simple", "pipe_in_company", "no_bullet_fallback", "no_overlap_fallback"])
def test_extract_company(header, full_title, expected):
    assert _extract_company(header, full_title) == expected


def test_extract_company_with_no_pipe_returns_the_whole_title():
    """
    Documents current behaviour rather than endorsing it. rpartition on a string
    with no "|" returns the original as its third element, so a page titled
    "Data Engineer | LinkedIn" reports the position as the company, and
    _extract_header then leaves position_name null. Change the expectation here
    if the extract should report None instead.
    """
    assert _extract_company("no bullet", "Data Engineer") == "Data Engineer"


# --------------------------------------------------------------------------
# _extract_location
# --------------------------------------------------------------------------

def test_location_sits_between_the_title_and_the_date():
    header = "Data Engineer Buenos Aires, Argentina · hace 3 meses"

    assert _extract_location(header, "Data Engineer") == "Buenos Aires, Argentina"


def test_location_uses_the_last_occurrence_of_the_title():
    """
    rfind, not find: the page title appears once in <title> and again in the
    posting header, and the location follows the second one.
    """
    header = "Data Engineer | Acme | LinkedIn Data Engineer Buenos Aires · hace 3 meses"

    assert _extract_location(header, "Data Engineer") == "Buenos Aires"


def test_location_without_the_date_anchor_is_none():
    assert _extract_location("Data Engineer Buenos Aires", "Data Engineer") is None


def test_location_handles_the_shared_posting_wording():
    """The anchor allows an optional "Compartido" between the dot and "hace"."""
    header = "Data Engineer Buenos Aires · Compartido hace 2 semanas"

    assert _extract_location(header, "Data Engineer") == "Buenos Aires"


def test_location_with_no_title_keeps_the_whole_segment():
    header = "Buenos Aires · hace 3 meses"

    assert _extract_location(header, None) == "Buenos Aires"


# --------------------------------------------------------------------------
# _extract_body
# --------------------------------------------------------------------------

def test_body_starts_after_the_anchor():
    cleaned = (
        f"nav junk {BODY_START_ANCHOR} the real description "
        f"{BODY_END_ANCHORS[0]} rail"
    )

    assert _extract_body(cleaned) == "the real description"


def test_body_without_the_start_anchor_is_none():
    assert _extract_body("nav junk with no anchor at all") is None


def test_body_runs_to_the_end_when_no_end_anchor_appears():
    cleaned = f"nav {BODY_START_ANCHOR} the real description"

    assert _extract_body(cleaned) == "the real description"


def test_body_cuts_at_the_earliest_end_anchor():
    """
    min() across every end anchor, not the first one found in the tuple: two
    anchors can both appear and the description stops at whichever comes first
    in the text. The anchor placed first here is last in the tuple on purpose,
    so tuple order winning would fail the test.
    """
    cleaned = (
        f"nav {BODY_START_ANCHOR} the real description "
        f"{BODY_END_ANCHORS[-1]} rail junk "
        f"{BODY_END_ANCHORS[0]} more junk"
    )

    assert _extract_body(cleaned) == "the real description"


# --------------------------------------------------------------------------
# extract_from_html, over a whole synthetic page
# --------------------------------------------------------------------------

def test_extract_from_html_reads_the_header():
    result = extract_from_html(make_page())
    header = result["header"]

    assert header["position_name"] == "Data Engineer"
    assert header["company_name"] == "Acme"
    assert header["posted_days_ago"] == 90
    assert header["posted_raw"] == "hace 3 meses"
    assert header["modality"] == MODALITIES[0]
    assert header["contract_type"] == CONTRACT_TYPES[0]
    assert header["linkedin_job_id"] == 4231234567


def test_extract_from_html_keeps_the_rail_out_of_the_body():
    result = extract_from_html(make_page())

    assert result["body"].startswith("Buscamos un ingeniero de datos.")
    assert "rail junk from another posting" not in result["body"]
    assert BODY_END_ANCHORS[0] not in result["body"]


def test_extract_from_html_drops_style_and_script_text():
    result = extract_from_html(make_page())

    assert "color: red" not in result["body"]


@pytest.mark.parametrize("modality", MODALITIES)
def test_extract_from_html_reads_every_modality(modality):
    page = make_page(
        subheader=f"Data Engineer Acme • Buenos Aires · hace 3 meses · {modality}"
    )

    assert extract_from_html(page)["header"]["modality"] == modality


def test_extract_from_html_leaves_absent_fields_null():
    """A posting that names no modality or contract type reports neither."""
    page = make_page(subheader="Data Engineer Acme • Buenos Aires · hace 3 meses")
    header = extract_from_html(page)["header"]

    assert header["modality"] is None
    assert header["contract_type"] is None


def test_a_body_exactly_at_the_minimum_is_accepted():
    """
    The guard is "< MIN_BODY_LENGTH", so the boundary length itself is valid.
    One character shorter is the rejection case, which needs pytest.raises.
    """
    page = make_page(body="x" * MIN_BODY_LENGTH)

    assert len(extract_from_html(page)["body"]) == MIN_BODY_LENGTH


def test_extract_from_html_falls_back_to_the_pre_pipe_position():
    """
    Title ending in a pipe leaves no company after it, and the subheader shares
    no suffix with the title, so company stays null and the position is read
    from the half before the last pipe rather than the half after it.
    """
    page = make_page(
        title="Data Engineer |",
        subheader="Data Engineer Acme • Buenos Aires · hace 3 meses",
    )
    header = extract_from_html(page)["header"]

    assert header["company_name"] is None
    assert header["position_name"] == "Data Engineer"


def test_extract_from_html_below_the_minimum_raises():
    """One character under the guard is the rejection the boundary test omits."""
    page = make_page(body="x" * (MIN_BODY_LENGTH - 1))

    with pytest.raises(JobDescriptionNotFound):
        extract_from_html(page)


# --------------------------------------------------------------------------
# _read_mhtml and extract_from_file
# --------------------------------------------------------------------------

def make_mhtml(
    html=None,
    snapshot_url="https://www.linkedin.com/jobs/view/4231234567/",
    with_html_part=True,
):
    """
    Minimal single-file MHTML archive, the shape a browser writes on save.

    A MIME container whose first part is the page and whose trailing image part
    stands in for the assets _read_mhtml must walk past. The parts declare no
    charset and ride 8bit, matching the save that forced the hand decode; the
    origin lives in the Snapshot-Content-Location header, not the save comment.
    """
    if html is None:
        html = make_page(source_url=snapshot_url)

    header = (
        "From: <Saved by Blink>\r\n"
        f"Snapshot-Content-Location: {snapshot_url}\r\n"
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/related; boundary="----BOUND"\r\n'
        "\r\n"
    )
    image_part = (
        "------BOUND\r\n"
        "Content-Type: image/png\r\n"
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "iVBORw0KGgo=\r\n"
    )
    html_part = (
        "------BOUND\r\n"
        "Content-Type: text/html\r\n"
        "Content-Transfer-Encoding: 8bit\r\n"
        "\r\n"
        f"{html}\r\n"
    )

    parts = [header]
    if with_html_part:
        parts.append(html_part)
    parts.append(image_part)
    parts.append("------BOUND--\r\n")

    return "".join(parts).encode("utf-8")


def test_read_mhtml_returns_the_html_and_the_snapshot_source(tmp_path):
    path = tmp_path / "posting.mhtml"
    path.write_bytes(make_mhtml())

    html_content, source = _read_mhtml(path)

    assert BODY_START_ANCHOR in html_content
    assert source == {
        "source_url": "https://www.linkedin.com/jobs/view/4231234567/",
        "linkedin_job_id": 4231234567,
    }


def test_read_mhtml_picks_the_html_part_past_the_image(tmp_path):
    """walk() must skip the image part and land on text/html, not the first part."""
    path = tmp_path / "posting.mhtml"
    path.write_bytes(make_mhtml())

    html_content, _ = _read_mhtml(path)

    assert html_content.startswith("<!-- saved from url")


def test_read_mhtml_without_an_html_part_raises(tmp_path):
    path = tmp_path / "imageonly.mhtml"
    path.write_bytes(make_mhtml(with_html_part=False))

    with pytest.raises(JobDescriptionNotFound):
        _read_mhtml(path)


def test_extract_from_file_reads_an_mhtml_archive(tmp_path):
    path = tmp_path / "posting.mhtml"
    path.write_bytes(make_mhtml())

    result = extract_from_file(path)

    assert result["header"]["linkedin_job_id"] == 4231234567
    assert result["body"].startswith("Buscamos un ingeniero de datos.")


def test_extract_from_file_reads_a_plain_html_file(tmp_path):
    path = tmp_path / "posting.html"
    path.write_text(make_page(), encoding="utf-8")

    result = extract_from_file(path)

    assert result["header"]["linkedin_job_id"] == 4231234567
    assert result["body"].startswith("Buscamos un ingeniero de datos.")


def test_extract_from_file_stamps_the_scrape_date_from_the_mtime(tmp_path):
    """The scrape date is the file's mtime, taken as a UTC calendar date."""
    path = tmp_path / "posting.html"
    path.write_text(make_page(), encoding="utf-8")

    when = datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc).timestamp()
    os.utime(path, (when, when))

    result = extract_from_file(path)

    assert result["scrape_date"] == "2026-03-14"
