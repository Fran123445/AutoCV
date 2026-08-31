"""Build renderer-independent resume documents from candidate data."""

import sqlite3

from datetime import date

from llm.client import LLMClient
from llm.tasks.resume.models import (
    ResumePromptContext,
    ResumePromptExperience,
    ResumePromptProject,
    ResumePromptTag,
)
from llm.tasks.resume.write import write_resume

from .dates import parse_date
from .localization import (
    localize_language_name,
    localize_proficiency_level,
    resolve_locale,
)
from .models import (
    ResumeDocument,
    ResumeEducation,
    ResumeExperience,
    ResumeLanguage,
    ResumeLink,
    ResumeProfile,
    ResumeProject,
    ResumeSkillGroup,
)


def _tenure_months(start: str | None, end: str | None) -> int | None:
    """Whole months between two stored dates, counting an absent end as today."""

    first = parse_date(start)

    if first is None:
        return None

    last = parse_date(end) or date.today()

    return max((last.year - first.year) * 12 + last.month - first.month, 0)


def _build_profile(
    connection: sqlite3.Connection,
    user_id: int,
) -> ResumeProfile:
    """Build the resume header from the candidate profile and links."""

    profile = connection.execute(
        """
        SELECT full_name, email, phone, location
        FROM FactUser
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()

    if profile is None:
        raise ValueError(f"candidate not found: {user_id}")

    full_name, email, phone, location = profile

    if full_name is None:
        raise ValueError(f"candidate {user_id} has no full name")

    links = connection.execute(
        """
        SELECT kind, url
        FROM UserLink
        WHERE user_id = ?
        ORDER BY kind
        """,
        (user_id,),
    ).fetchall()

    return ResumeProfile(
        full_name=full_name,
        email=email,
        phone=phone,
        location=location,
        links=[ResumeLink(kind=kind, url=url) for kind, url in links],
    )


def _build_education(
    connection: sqlite3.Connection,
    user_id: int,
    language: str,
) -> list[ResumeEducation]:
    """Build education entries using the requested display language."""

    education = connection.execute(
        """
        SELECT COALESCE(localized.name, english.name),
               ue.institution, ue.gpa, ue.start_date, ue.end_date
        FROM UserEducation AS ue
        JOIN DimDegree AS d ON d.id = ue.degree_id
        LEFT JOIN DimDegreeTranslation AS localized
            ON localized.degree_id = d.id AND localized.locale = ?
        LEFT JOIN DimDegreeTranslation AS english
            ON english.degree_id = d.id AND english.locale = 'en'
        WHERE ue.user_id = ?
        ORDER BY
            ue.end_date IS NULL DESC,
            ue.end_date DESC,
            ue.start_date DESC,
            d.name,
            ue.institution
        """,
        (resolve_locale(language).code, user_id),
    ).fetchall()

    return [
        ResumeEducation(
            degree=degree,
            institution=institution,
            gpa=gpa,
            start_date=start_date,
            end_date=end_date,
        )
        for degree, institution, gpa, start_date, end_date in education
    ]


def _build_languages(
    connection: sqlite3.Connection,
    user_id: int,
) -> list[ResumeLanguage]:
    """Build language entries from the candidate's stored languages."""

    # Load order, which is the order they were written in the file: a candidate
    # lists their native language first, and alphabetical would bury it.
    languages = connection.execute(
        """
        SELECT name, level
        FROM UserLanguage
        WHERE user_id = ?
        ORDER BY rowid
        """,
        (user_id,),
    ).fetchall()

    return [ResumeLanguage(name=name, level=level) for name, level in languages]


def _build_prompt_experience(
    connection: sqlite3.Connection,
    user_id: int,
) -> list[ResumePromptExperience]:
    """Build the work history the writer reads, current positions first."""

    experience = connection.execute(
        """
        SELECT e.id, c.company_name, r.role_name, e.job_title, s.label,
               e.start_date, e.end_date, e.day_to_day
        FROM FactExperience AS e
        LEFT JOIN DimCompany AS c ON c.id = e.company_id
        LEFT JOIN DimRole AS r ON r.id = e.role_id
        LEFT JOIN DimSeniority AS s ON s.id = e.seniority_id
        WHERE e.user_id = ?
        ORDER BY e.end_date IS NULL DESC, e.end_date DESC, e.start_date DESC
        """,
        (user_id,),
    ).fetchall()

    return [
        ResumePromptExperience(
            source_experience_id=experience_id,
            # Both are NOT NULL on the CV and nullable in the base: a position
            # with no company is still a position, and printing a hole in the
            # header is what makes it obvious the file needs fixing.
            company=company or "(unknown)",
            role=role or "(unknown)",
            job_title=job_title,
            seniority=seniority,
            start_date=start_date,
            end_date=end_date,
            tenure_months=_tenure_months(start_date, end_date),
            day_to_day=day_to_day,
        )
        for (
            experience_id,
            company,
            role,
            job_title,
            seniority,
            start_date,
            end_date,
            day_to_day,
        ) in experience
    ]


def _build_prompt_tags(
    connection: sqlite3.Connection,
    user_id: int,
    bridge: str,
    dimension: str,
    name_column: str,
    dimension_id: str,
) -> dict[int, list[ResumePromptTag]]:
    """Gather one bridge's tags for every project the candidate has, by project."""

    tags: dict[int, list[ResumePromptTag]] = {}

    for project_id, name, descr in connection.execute(
        f"""
        SELECT b.project_id, d.{name_column}, b.descr
        FROM {bridge} AS b
        JOIN {dimension} AS d ON d.id = b.{dimension_id}
        JOIN Project AS p ON p.id = b.project_id
        WHERE p.user_id = ?
        ORDER BY d.{name_column}
        """,
        (user_id,),
    ):
        tags.setdefault(project_id, []).append(ResumePromptTag(name=name, descr=descr))

    return tags


def _build_prompt_projects(
    connection: sqlite3.Connection,
    user_id: int,
    personal: bool,
    technologies: dict[int, list[ResumePromptTag]],
    concepts: dict[int, list[ResumePromptTag]],
) -> list[ResumePromptProject]:
    """Build one side of the candidate's projects, personal or done at a job."""

    projects = connection.execute(
        f"""
        SELECT p.id, p.experience_id, p.task_desc, p.source_path
        FROM Project AS p
        WHERE p.user_id = ? AND p.experience_id IS {"" if personal else "NOT "}NULL
        ORDER BY p.id
        """,
        (user_id,),
    ).fetchall()

    return [
        ResumePromptProject(
            source_project_id=project_id,
            source_experience_id=experience_id,
            description=task_desc,
            source_path=source_path,
            technologies=technologies.get(project_id, []),
            concepts=concepts.get(project_id, []),
        )
        for project_id, experience_id, task_desc, source_path in projects
    ]


def _build_prompt_skills(
    connection: sqlite3.Connection,
    user_id: int,
) -> list[str]:
    """Everything the candidate is on record as knowing, for the skills block."""

    skills = connection.execute(
        """
        SELECT d.name FROM UserTechnologies AS u
        JOIN DimTechnologies AS d ON d.id = u.technology_id
        WHERE u.user_id = ?
        UNION
        SELECT d.concept_name FROM UserConcepts AS u
        JOIN DimConcepts AS d ON d.id = u.concept_id
        WHERE u.user_id = ?
        ORDER BY 1
        """,
        (user_id, user_id),
    )

    return [name for name, in skills]


def _build_prompt_context(
    connection: sqlite3.Connection,
    user_id: int,
    job_id: int,
) -> ResumePromptContext:
    """Gather everything the writer reads about one candidate and one posting."""

    job = connection.execute(
        "SELECT raw_text, language FROM FactJob WHERE id = ?",
        (job_id,),
    ).fetchone()

    if job is None:
        raise ValueError(f"job not found: {job_id}")

    language = resolve_locale(job[1]).code

    technologies = _build_prompt_tags(
        connection, user_id, "ProjectTechnologies", "DimTechnologies", "name", "technology_id"
    )
    concepts = _build_prompt_tags(
        connection, user_id, "ProjectConcepts", "DimConcepts", "concept_name", "concept_id"
    )

    return ResumePromptContext(
        job_description=job[0],
        language=language,
        education=_build_education(connection, user_id, language),
        languages=_build_languages(connection, user_id),
        experience=_build_prompt_experience(connection, user_id),
        work_projects=_build_prompt_projects(connection, user_id, False, technologies, concepts),
        personal_projects=_build_prompt_projects(
            connection, user_id, True, technologies, concepts
        ),
        skills=_build_prompt_skills(connection, user_id),
    )


def generate_resume(
    connection: sqlite3.Connection,
    user_id: int,
    job_id: int,
    llm_client: LLMClient,
) -> ResumeDocument:
    """Build one candidate's resume for one job posting.

    The header, the education and the languages are printed as the candidate
    wrote them and never go through the writer.  Everything else is written
    against this posting, so the same candidate and a different job_id produce
    a different document from the same rows.

    Args:
        connection: Open connection to the candidate database.
        user_id: Candidate whose resume should be built.
        job_id: Posting the resume is written against.

    Returns:
        A renderer-independent resume document.

    Raises:
        ValueError: If the candidate or the posting does not exist, or the
            candidate has no name.
    """
    context = _build_prompt_context(connection, user_id, job_id)
    written = write_resume(context, llm_client)

    bullets = {entry.source_experience_id: entry.bullets for entry in written.work_bullets}

    return ResumeDocument(
        profile=_build_profile(connection, user_id),
        language=resolve_locale(context.language).code,
        summary=written.summary,
        skills=[
            ResumeSkillGroup(label=group.label, items=group.items) for group in written.skills
        ],
        experience=[
            ResumeExperience(
                company=entry.company,
                role=entry.role,
                job_title=entry.job_title,
                start_date=entry.start_date,
                end_date=entry.end_date,
                bullets=bullets.get(entry.source_experience_id, []),
                source_experience_id=entry.source_experience_id,
            )
            for entry in context.experience
        ],
        projects=[
            ResumeProject(
                title=project.title,
                bullets=project.bullets,
                technologies=project.technologies,
                source_project_id=project.source_project_id,
            )
            for project in written.personal_bullets
        ],
        education=context.education,
        languages=[
            ResumeLanguage(
                name=localize_language_name(language.name, context.language),
                level=(
                    localize_proficiency_level(language.level, context.language)
                    if language.level
                    else None
                ),
            )
            for language in context.languages
        ],
    )
