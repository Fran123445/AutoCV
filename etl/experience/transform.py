import re

from etl.experience.models import Experience
from llm.tasks.experience.narrator.narrate import narrate
from llm.tasks.experience.tech_identifier.identify import identify_technologies

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

def _transform_profile(experience: Experience) -> dict:
    """
    Map the profile block onto FactUser + UserLink shape.

    Args:
        experience (Experience): The parsed experience file.

    Returns:
        dict: full_name, email, phone, location, birth_date, and links
            (kind/url pairs) for FactUser and UserLink.
    """
    profile = experience.profile

    return {
        "full_name": profile.full_name,
        "email": profile.email,
        "phone": profile.phone,
        "location": profile.location,
        "birth_date": _parse_date(profile.birth_date),
        "links": [{"kind": link.kind, "url": link.url} for link in profile.link],
    }

def _transform_education(experience: Experience) -> list[dict]:
    """
    Map each education block onto UserEducation shape.

    DimDegree is seeded from seeds/degrees.json rather than classified here:
    the degree name is expected already canonical and passes through as-is.
    An unrecognised one is not this stage's problem to catch — load resolves
    it against DimDegree and raises UnknownSeedValue there.

    Args:
        experience (Experience): The parsed experience file.

    Returns:
        list[dict]: degree, institution, start_date, end_date per block.
    """
    return [
        {
            "degree": education.degree,
            "institution": education.institution,
            "start_date": _parse_date(education.start),
            "end_date": _parse_date(education.end),
        }
        for education in experience.education
    ]

def _transform_job(experience: Experience):
    pass

def _transform_job_day_to_day(day_to_day: str | None) -> dict | None:
    """
    Identify and rewrite what one job consisted of day to day.

    Two passes rather than one, for a reason that is about prompt size and not
    about the reading: the technology names run to 13 KB with their aliases and
    the concept names to 26 KB, and a single prompt carrying both would bury the
    account it is meant to be about. The technologies go first because the
    rewrite reads better once they are named.

    Both passes are single, unlike the jobs and projects sides. A review pass
    recovers entries scattered over a long document, and this block is two
    paragraphs.

    Args:
        day_to_day (str | None): The job's day_to_day block, as written in
            experience.toml. None when the block is absent or empty.

    Returns:
        dict | None: The technologies worked with and the narrative, or None
            when the file left the block out. The tags load into
            UserTechnologies and UserConcepts, the prose into
            FactExperience.day_to_day.
    """
    if day_to_day is None:
        return None

    technologies = identify_technologies(day_to_day)
    narrative = narrate(technologies.technologies, day_to_day)

    return {
        "technologies": technologies.model_dump(),
        "narrative": narrative.model_dump(),
    }

def _transform_job_project(project_desc: str):
    pass

def transform(experience: Experience):
    profile = _transform_profile(experience)
    education = _transform_education(experience)
    job = _transform_job(experience)