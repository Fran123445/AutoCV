"""Reading the localized dates a resume prints.

Stored dates are strings, either "YYYY-MM" or "YYYY-MM-DD", and both the
document builder and a renderer have to read them. They live here rather than
on either side: generator imports the resume-writing task and a renderer pulls
in a template engine, so parking the parsing on one would drag that dependency
into the other.
"""

from datetime import date

from .localization import resolve_locale


def parse_date(stamp: str | None) -> date | None:
    """Read a stored date, which may be a month or a full day."""

    if not stamp:
        return None

    parts = stamp.split("-")

    return date(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 1)


def month_year(stamp: str | None, absent: str, language: str = "en") -> str:
    """Render a stored date the way an entry heading prints it."""

    parsed = parse_date(stamp)
    locale = resolve_locale(language)

    return f"{locale.months[parsed.month - 1]} {parsed.year}" if parsed else absent


def span(start: str | None, end: str | None, language: str = "en") -> str:
    """Render one entry's dates, with an absent end read as ongoing."""

    locale = resolve_locale(language)

    return f"{month_year(start, '?', language)} - {month_year(end, locale.present, language)}"
