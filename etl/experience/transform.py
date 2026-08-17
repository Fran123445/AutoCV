import re

from etl.experience.models import Experience

_DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def _parse_date(raw_date: str | None) -> str | None:
    """
    Validate a TOML date and pass it through as-is.

    Columns are TEXT storing ISO 8601, so no conversion is needed — only
    validation, plus mapping "current" to the null the schema uses for
    ongoing jobs and education.

    Args:
        raw_date (str | None): "YYYY", "YYYY-MM", "YYYY-MM-DD" or "current".

    Returns:
        str | None: The date unchanged, or None for "current"/None.

    Raises:
        ValueError: raw_date does not match ISO 8601.
    """
    if raw_date is None or raw_date == "current":
        return None
    if not _DATE_RE.match(raw_date):
        raise ValueError(f"invalid date: {raw_date!r}")
    return raw_date

def _transform_profile(experience: Experience):
    pass

def _transform_education(experience: Experience):
    pass

def _transform_job(experience: Experience):
    pass

def _transform_job_day_to_day(day_to_day: str):
    pass

def _transform_job_project(project_desc: str):
    pass

def transform(experience: Experience):
    profile = _transform_profile(experience)
    education = _transform_education(experience)
    job = _transform_job(experience)