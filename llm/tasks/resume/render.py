"""
Turns the structured resume context into the candidate block the writer reads.

Every narrative here was written by an earlier pass, so unlike the projects
side there is no evidence to assemble and the work is labelling it. The ids are
part of that labelling rather than bookkeeping left in by accident: the writer
returns its bullets keyed by them, so a position it cannot name is a position
it cannot write for.
"""

from resume_generator.models import ResumeEducation, ResumeLanguage

from .models import (
    ResumePromptContext,
    ResumePromptExperience,
    ResumePromptProject,
    ResumePromptTag,
)


# Every narrative reaching here is a few sentences from an earlier pass. The cap
# is for the one that came back long, not for the normal case.
MAX_NARRATIVE_CHARS = 1_500


def _render_dates(start: str | None, end: str | None) -> str:
    """
    Render one entry's span.

    Args:
        start (str | None): Start date as stored.
        end (str | None): End date as stored, absent while still ongoing.

    Returns:
        str: The span, with an absent end read as ongoing.
    """
    if start is None and end is None:
        return "(not given)"

    return f"{start or '(not given)'} to {end or 'present'}"


def _render_tags(tags: list[ResumePromptTag]) -> str:
    """
    Render one project's technologies or concepts, one per line.

    The phrase saying what a tag did on this project is worth more to the
    writer than the name: postgresql is on half the projects, "the queue the
    workers read from" is on one. Listed rather than joined into a line,
    because names with phrases hanging off some of them stop being readable at
    around ten tags.

    Args:
        tags (list[ResumePromptTag]): The tags, already ordered.

    Returns:
        str: One line per tag, or a marker when there are none.
    """
    if not tags:
        return "(none)"

    return "\n".join(
        f"* {tag.name}: {tag.descr}" if tag.descr else f"* {tag.name}" for tag in tags
    )


def _render_folder(source_path: str | None) -> str:
    """
    Render the last segment of a project's path.

    Given so the writer can see what it is renaming away from, not so it can
    use it: a folder is named by someone who already knows what is inside it,
    and reads on a CV as either an abbreviation or a private joke.

    Args:
        source_path (str | None): Where the project was read from, if known.

    Returns:
        str: The folder name, or a marker when there is no path.
    """
    if not source_path:
        return "(not given)"

    return source_path.replace("\\", "/").rstrip("/").split("/")[-1] or "(not given)"


def _render_project(project: ResumePromptProject) -> str:
    """
    Render one project as a labelled entry.

    Args:
        project (ResumePromptProject): The project to render.

    Returns:
        str: The entry, headed by the id the writer keys its bullets on.
    """
    return "\n\n".join(
        [
            f"--- project {project.source_project_id} ---\n"
            f"folder name: {_render_folder(project.source_path)}\n"
            f"description: {project.description[:MAX_NARRATIVE_CHARS]}",
            f"technologies:\n{_render_tags(project.technologies)}",
            f"concepts:\n{_render_tags(project.concepts)}",
        ]
    )


def _render_experience(
    experience: ResumePromptExperience,
    projects: list[ResumePromptProject],
) -> str:
    """
    Render one position, with the projects worked on during it beneath it.

    Nested rather than listed apart because the writer keys a position's
    bullets by its id alone: a project floating in its own section would be
    evidence the model has no way to attach.

    Args:
        experience (ResumePromptExperience): The position to render.
        projects (list[ResumePromptProject]): Its projects, possibly none.

    Returns:
        str: The entry, headed by the id the writer keys its bullets on.
    """
    day_to_day = experience.day_to_day

    rendered = "\n".join(
        [
            f"--- experience {experience.source_experience_id} ---",
            f"company: {experience.company}",
            f"job title: {experience.job_title or '(not given)'}",
            # The taxonomy's name for the position, not the printed one above.
            f"role category: {experience.role}",
            f"seniority: {experience.seniority or '(not given)'}",
            f"dates: {_render_dates(experience.start_date, experience.end_date)}",
            f"tenure: {f'{experience.tenure_months} months' if experience.tenure_months else '(not given)'}",
            f"day to day: {day_to_day[:MAX_NARRATIVE_CHARS] if day_to_day else '(none)'}",
        ]
    )

    if projects:
        rendered += "\n\nprojects worked on in this position:\n\n" + "\n\n".join(
            _render_project(project) for project in projects
        )

    return rendered


def _render_education(education: list[ResumeEducation]) -> str:
    """
    Render the education entries, one per line.

    No ids: the writer returns nothing keyed to a degree, so these are here to
    inform the summary rather than to be written back.

    Args:
        education (list[ResumeEducation]): The entries, already ordered.

    Returns:
        str: One line per entry, or a marker when there are none.
    """
    if not education:
        return "(none given)"

    return "\n".join(
        f"* {entry.degree}, {entry.institution or '(institution not given)'} "
        f"({_render_dates(entry.start_date, entry.end_date)})"
        + (f", grade point average {entry.gpa}" if entry.gpa else "")
        for entry in education
    )


def _render_languages(languages: list[ResumeLanguage]) -> str:
    """
    Render the spoken languages, one per line.

    Printed on the CV verbatim from the record, so like the education these are
    here to inform the summary rather than to be written back. Worth the lines
    anyway: a posting that asks for a language is asking about a requirement the
    candidate either meets or does not.

    Args:
        languages (list[ResumeLanguage]): The languages, already ordered.

    Returns:
        str: One line per language, or a marker when there are none.
    """
    if not languages:
        return "(none given)"

    return "\n".join(
        f"* {language.name}: {language.level}" if language.level else f"* {language.name}"
        for language in languages
    )


def _render_skills(skills: list[str]) -> str:
    """
    Render everything the candidate is on record as knowing.

    Flat, rather than sorted into the groups the block is printed in. Which
    grouping earns its place depends on the posting being written against, so
    one fixed here would be one the writer has to argue with rather than one
    it can choose.

    Args:
        skills (list[str]): The names, already ordered.

    Returns:
        str: One line per skill, or a marker when there are none.
    """
    if not skills:
        return "(none given)"

    return "\n".join(f"* {skill}" for skill in skills)


def render_candidate(context: ResumePromptContext) -> str:
    """
    Render the candidate half of the writer's prompt.

    The job description is left to the caller to fence separately: the two
    halves are read against each other, and the model has to be able to tell
    the posting's claims from the candidate's. The profile is left out
    altogether, since nothing the writer returns is drawn from it and the
    generator already carries it into the document unchanged.

    Args:
        context (ResumePromptContext): Candidate and job data for one resume.

    Returns:
        str: The candidate block, labelled section by section.
    """
    by_experience: dict[int, list[ResumePromptProject]] = {}
    for project in context.work_projects:
        by_experience.setdefault(project.source_experience_id, []).append(project)

    experience = "\n\n".join(
        _render_experience(entry, by_experience.pop(entry.source_experience_id, []))
        for entry in context.experience
    )

    personal = "\n\n".join(_render_project(project) for project in context.personal_projects)

    sections = [
        f"[skills on record]\n{_render_skills(context.skills)}",
        f"[education]\n{_render_education(context.education)}",
        f"[languages spoken]\n{_render_languages(context.languages)}",
        f"[work history]\n{experience or '(none given)'}",
        f"[personal projects]\n{personal or '(none given)'}",
    ]

    # A work project whose position was not supplied cannot back any bullet,
    # since those are keyed by experience id. Rendered anyway rather than
    # dropped, because it can still tell the summary what the candidate has done.
    orphans = [project for group in by_experience.values() for project in group]
    if orphans:
        sections.append(
            "[work projects with no position given]\n"
            + "\n\n".join(_render_project(project) for project in orphans)
        )

    return "\n\n".join(sections)
