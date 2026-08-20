import re

from etl.experience.models import Experience
from llm.tasks.experience.day_to_day_narrator.narrate import narrate as narrate_day_to_day
from llm.tasks.experience.project_describer.describe import describe
from llm.tasks.experience.project_narrator.narrate import narrate as narrate_project
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
        list[dict]: degree, institution, gpa, start_date, end_date per block.
    """
    return [
        {
            "degree": education.degree,
            "institution": education.institution,
            "gpa": education.gpa,
            "start_date": _parse_date(education.start),
            "end_date": _parse_date(education.end),
        }
        for education in experience.education
    ]

def _transform_language(experience: Experience) -> list[dict]:
    """
    Map each language block onto UserLanguage shape.

    Nothing to canonicalise: there is no dim behind these and the level is
    written the way the CV should print it, so the block passes through under
    the column names. A block with no name is dropped here rather than at load,
    since UserLanguage.name is the key and a blank one is a line the candidate
    left in the template.

    Args:
        experience (Experience): The parsed experience file.

    Returns:
        list[dict]: name and level per named block.
    """
    return [
        {"name": language.name, "level": language.level}
        for language in experience.language
        if language.name is not None
    ]

def _transform_job(experience: Experience) -> list[dict]:
    """
    Map each job block onto FactExperience shape, with its projects.

    Company, role and seniority pass through untouched: they are expected
    already canonical, and an unrecognised one is load's to catch against its
    dim, not this stage's. The title passes through for the opposite reason:
    it is what the candidate was actually called, matches no dim, and is the
    only one of the two that a CV can print.

    Args:
        experience (Experience): The parsed experience file.

    Returns:
        list[dict]: id, company, title, role, seniority, dates, the identified
            day_to_day and the identified projects, per block. The ids are the
            file's own and are what load dedupes on, since a job has no
            linkedin_job_id and a project born here has no source_path.
    """
    return [
        {
            "id": job.id,
            "company": job.company,
            "title": job.title,
            "role": job.role,
            "seniority": job.seniority,
            "start_date": _parse_date(job.start),
            "end_date": _parse_date(job.end),
            "day_to_day": _transform_job_day_to_day(job.day_to_day),
            "projects": [
                {
                    "id": project.id,
                    # Kept even when None (not dropped): Project.task_desc is
                    # NOT NULL, so load must reject this row itself.
                    "identified": _transform_job_project(project.story),
                }
                for project in job.project
            ],
        }
        for job in experience.job
    ]

def _transform_job_day_to_day(day_to_day: str | None) -> dict | None:
    """
    Identify and rewrite what one job consisted of day to day.

    Two passes rather than one: the technology names run to 13 KB with their
    aliases and the concept names to 26 KB, and a single prompt carrying both
    would bury the account it is meant to be about. Technologies go first
    because the rewrite reads better once they are named.

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

    technologies = identify_technologies(day_to_day, "day_to_day")
    narrative = narrate_day_to_day(technologies.technologies, day_to_day)

    return {
        "technologies": technologies.model_dump(),
        "narrative": narrative.model_dump(),
    }

def _transform_job_project(story: str | None) -> dict | None:
    """
    Identify one project a candidate did at a job, from their account of it.

    Three passes, the same shape the projects pipeline runs over a repository:
    technologies come first because the narrative reads better once they are
    named, and descriptions come last because there is nothing to describe
    until both lists exist. What's missing here is the sampling step, since
    the evidence is one block of prose rather than a tree of files to choose
    from.

    Args:
        story (str | None): The project's story block, as written in
            experience.toml. None when the block is absent or empty.

    Returns:
        dict | None: The technologies, the narrative and the per-item
            descriptions, or None when the file left the block out. Project
            rows born here carry a null source_path: there is no repository
            behind them, and the block's id is what load dedupes on.
    """
    if story is None:
        return None

    technologies = identify_technologies(story, "project")
    narrative = narrate_project(technologies.technologies, story)
    descriptions = describe(
        narrative.task_desc,
        technologies.technologies,
        narrative.concepts,
        story,
    )

    return {
        "technologies": technologies.model_dump(),
        "narrative": narrative.model_dump(),
        "descriptions": descriptions,
    }

def transform(experience: Experience) -> dict:
    """
    Transform one experience file into the rows the load stage writes.

    The blocks are independent of each other and of the order they run in:
    only the jobs cost anything, and they cost everything. The profile is a
    rename and a date parse, the education adds nothing to that, and the
    languages are a rename alone.

    Args:
        experience (Experience): The parsed experience file.

    Returns:
        dict: The identified file. profile fills FactUser and UserLink,
            education fills UserEducation, languages fill UserLanguage, and
            jobs fill FactExperience and the Project rows hanging off it, along
            with the user's technology and concept rollups.
    """
    return {
        "profile": _transform_profile(experience),
        "education": _transform_education(experience),
        "languages": _transform_language(experience),
        "jobs": _transform_job(experience),
    }