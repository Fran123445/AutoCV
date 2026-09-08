import pytest

from etl.jobs.config import (
    BODY_END_ANCHORS,
    BODY_START_ANCHOR,
    CONTRACT_TYPES,
    MIN_BODY_LENGTH,
    MODALITIES,
)
from etl.jobs.extract import JobDescriptionNotFound
from etl.jobs.extract.linkedin import (
    _clean_html,
    _extract_body,
    _extract_company,
    _extract_location,
    _extract_posted,
    _longest_common_suffix,
    extract,
)


def source_info(source_url="https://www.linkedin.com/jobs/view/4231234567/"):
    return {"source_url": source_url}


def make_page(
    title="Data Engineer | Acme",
    subheader=(
        f"Data Engineer Acme • Buenos Aires · hace 3 meses "
        f"· {MODALITIES[0]} · {CONTRACT_TYPES[0]}"
    ),
    body="Buscamos un ingeniero de datos. " * 20,
    end_anchor=BODY_END_ANCHORS[0],
):
    return (
        f"<html><head><title>{title} | LinkedIn</title>"
        f"<style>body {{ color: red; }}</style></head>"
        f"<body><p>{subheader}</p>"
        f"<p>{BODY_START_ANCHOR}</p><p>{body}</p>"
        f"<p>{end_anchor}</p><p>rail junk from another posting</p></body></html>"
    )


@pytest.mark.parametrize("html, expected", [
    ("<p>Hello world</p>", "Hello world"),
    ("<p>Hello     world</p>", "Hello world"),
    ("<p>Hello</p><p>world</p>", "Hello world"),
    ("<script>var x = 1;</script><p>Hello</p>", "Hello"),
    ("<style>p { color: red; }</style><p>Hello</p>", "Hello"),
    ("<noscript>enable js</noscript><p>Hello</p>", "Hello"),
    ("<p>   Hello   </p>", "Hello"),
])
def test_clean_html(html, expected):
    assert _clean_html(html) == expected


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
    ("· hace más de 1 año", 365),
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


@pytest.mark.parametrize("left, right, expected", [
    ("Acme Corp", "hello Acme Corp", "Acme Corp"),
    ("Data | Acme", "Buenos Acme", " Acme"),
    ("abc", "xyz", ""),
    ("", "abc", ""),
    ("abc", "", ""),
    ("Acme", "Acme", "Acme"),
])
def test_longest_common_suffix(left, right, expected):
    assert _longest_common_suffix(left, right) == expected


@pytest.mark.parametrize("header, full_title, expected", [
    ("Data Engineer Acme • Buenos Aires", "Data Engineer | Acme", "Acme"),
    ("Data Engineer Acme | Corp • Buenos Aires", "Data | Eng | Acme | Corp", "Acme | Corp"),
    ("Data Engineer, no bullet anywhere", "Data Engineer | Acme", "Acme"),
    ("Totally unrelated • Buenos Aires", "Data Engineer | Acme", "Acme"),
])
def test_extract_company(header, full_title, expected):
    assert _extract_company(header, full_title) == expected


def test_extract_location_rules():
    assert _extract_location(
        "Data Engineer Buenos Aires, Argentina · hace 3 meses",
        "Data Engineer",
    ) == "Buenos Aires, Argentina"
    assert _extract_location(
        "Data Engineer Buenos Aires · Compartido hace 2 semanas",
        "Data Engineer",
    ) == "Buenos Aires"
    assert _extract_location("Data Engineer Buenos Aires", "Data Engineer") is None


def test_extract_body_rules():
    cleaned = f"nav {BODY_START_ANCHOR} the real description {BODY_END_ANCHORS[0]} rail"
    assert _extract_body(cleaned) == "the real description"
    assert _extract_body("nav junk with no start anchor") is None

    cleaned = (
        f"nav {BODY_START_ANCHOR} the real description "
        f"{BODY_END_ANCHORS[-1]} rail junk {BODY_END_ANCHORS[0]} more junk"
    )
    assert _extract_body(cleaned) == "the real description"


def test_extract_reads_linkedin_header_and_body():
    result = extract(make_page(), source_info())
    header = result["header"]

    assert header["source"] == "linkedin"
    assert header["position_name"] == "Data Engineer"
    assert header["company_name"] == "Acme"
    assert header["posted_days_ago"] == 90
    assert header["modality"] == MODALITIES[0]
    assert header["contract_type"] == CONTRACT_TYPES[0]
    assert header["source_job_id"] == 4231234567
    assert result["body"].startswith("Buscamos un ingeniero de datos.")
    assert "rail junk from another posting" not in result["body"]
    assert "color: red" not in result["body"]


@pytest.mark.parametrize("modality", MODALITIES)
def test_extract_reads_every_modality(modality):
    page = make_page(
        subheader=f"Data Engineer Acme • Buenos Aires · hace 3 meses · {modality}"
    )
    assert extract(page, source_info())["header"]["modality"] == modality


def test_extract_leaves_absent_fields_null():
    page = make_page(subheader="Data Engineer Acme • Buenos Aires · hace 3 meses")
    header = extract(page, source_info())["header"]
    assert header["modality"] is None
    assert header["contract_type"] is None


def test_extract_accepts_the_minimum_body_length():
    page = make_page(body="x" * MIN_BODY_LENGTH)
    assert len(extract(page, source_info())["body"]) == MIN_BODY_LENGTH


def test_extract_falls_back_to_the_pre_pipe_position():
    page = make_page(
        title="Data Engineer |",
        subheader="Data Engineer Acme • Buenos Aires · hace 3 meses",
    )
    header = extract(page, source_info())["header"]
    assert header["company_name"] is None
    assert header["position_name"] == "Data Engineer"


def test_extract_rejects_a_short_body():
    page = make_page(body="x" * (MIN_BODY_LENGTH - 1))
    with pytest.raises(JobDescriptionNotFound):
        extract(page, source_info())
