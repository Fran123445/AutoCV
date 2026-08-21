from datetime import date

import pytest

from resume_generator.dates import month_year, parse_date, span


# --------------------------------------------------------------------------
# parse_date
# --------------------------------------------------------------------------

def test_a_month_stamp_defaults_the_day_to_the_first():
    """
    "YYYY-MM" carries no day, so the first of the month stands in. This is the
    anchor the headings read off; the day never prints, but date() needs one.
    """
    assert parse_date("2021-06") == date(2021, 6, 1)


def test_a_full_stamp_keeps_its_day():
    assert parse_date("2021-06-15") == date(2021, 6, 15)


@pytest.mark.parametrize("stamp", [None, ""], ids=["none", "empty"])
def test_an_absent_stamp_is_none(stamp):
    """Both None and "" mean no date: `not stamp` catches the pair together."""
    assert parse_date(stamp) is None


# --------------------------------------------------------------------------
# month_year
# --------------------------------------------------------------------------

def test_month_year_prints_the_abbreviated_month_and_year():
    assert month_year("2021-06", absent="?") == "Jun 2021"


def test_month_year_reads_january_off_the_low_edge_of_the_table():
    """Month 1 indexes MONTHS[0]; an off-by-one here would print the wrong name."""
    assert month_year("2021-01", absent="?") == "Jan 2021"


def test_month_year_reads_december_off_the_high_edge_of_the_table():
    assert month_year("2021-12", absent="?") == "Dec 2021"


def test_month_year_falls_back_to_the_absent_text_when_there_is_no_stamp():
    assert month_year(None, absent="Present") == "Present"


# --------------------------------------------------------------------------
# span
# --------------------------------------------------------------------------

def test_span_joins_both_ends():
    assert span("2019-03", "2021-06") == "Mar 2019 - Jun 2021"


def test_span_reads_a_missing_end_as_ongoing():
    """An absent end is a job still held, printed as "Present" not "?"."""
    assert span("2019-03", None) == "Mar 2019 - Present"


def test_span_marks_a_missing_start_with_a_question_mark():
    """The two ends carry different absent text: a start has no "Present" reading."""
    assert span(None, "2021-06") == "? - Jun 2021"
