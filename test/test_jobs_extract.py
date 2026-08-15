import pytest

from etl.jobs.extract import _extract_posted
from etl.jobs.extract import JobDescriptionNotFound, extract_from_html


@pytest.mark.parametrize("header, expected_days", [
    ("· hace 5 horas", 0),
    ("· hace 1 día", 1),
    ("· hace 2 semanas", 14),
    ("· hace 3 meses", 90),
    ("· hace más de 1 año", 365),
])
def test_three_months_is_ninety_days(header, expected_days):
    assert _extract_posted(header)["posted_days_ago"] == expected_days

    
def test_short_body_is_rejected():
    html = "<html><title>x | Acme | LinkedIn</title></html>"
    with pytest.raises(JobDescriptionNotFound):
        extract_from_html(html)