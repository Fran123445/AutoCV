"""Structured context passed to the resume-writing LLM, and what it returns."""

from pydantic import BaseModel, ConfigDict, Field

from resume_generator.models import ResumeEducation, ResumeLanguage


class _PromptBlock(BaseModel):
    """Common validation policy for LLM prompt data."""

    model_config = ConfigDict(extra="forbid")


class ResumePromptExperience(_PromptBlock):
    """One work-history entry supplied as context to the LLM."""

    source_experience_id: int
    company: str
    role: str
    job_title: str | None = None
    seniority: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    tenure_months: int | None = None
    day_to_day: str | None = None


class ResumePromptTag(_PromptBlock):
    """One technology or concept a project is evidence for."""

    name: str
    descr: str | None = None


class ResumePromptProject(_PromptBlock):
    """One project supplied as context to the LLM."""

    source_project_id: int
    description: str
    source_path: str | None = None
    source_experience_id: int | None = None
    technologies: list[ResumePromptTag] = Field(default_factory=list)
    concepts: list[ResumePromptTag] = Field(default_factory=list)


class ResumePromptContext(_PromptBlock):
    """Structured candidate and job data rendered into an LLM prompt."""

    job_description: str
    # The posting's language as FactJob stores it, null when it was too short
    # to tell. The CV is written in it, so it is job data rather than a setting.
    language: str | None = None
    education: list[ResumeEducation] = Field(default_factory=list)
    languages: list[ResumeLanguage] = Field(default_factory=list)
    experience: list[ResumePromptExperience] = Field(default_factory=list)
    work_projects: list[ResumePromptProject] = Field(default_factory=list)
    personal_projects: list[ResumePromptProject] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class ResumeSkillGroup(BaseModel):
    """One labelled row of the skills block."""

    label: str = Field(
        description="What this row of skills has in common, cased the way the CV's language cases a heading, as the reader's eye needs to land on it before the list: for example Languages, Data Engineering, Databases and Platforms, Testing and Tooling."
    )
    items: list[str] = Field(
        description="The skills on this row, ordered with the ones the posting asks for first."
    )


class ResumeWorkBullets(BaseModel):
    """The bullets written for one position in the work history."""

    source_experience_id: int = Field(
        description="The position these bullets belong to, taken from the id given with it."
    )
    bullets: list[str] = Field(
        description="What the candidate did in this position, one piece of work per bullet, each naming the mechanism that made it work."
    )


class ResumePersonalBullets(BaseModel):
    """The bullets written for one personal project, and how to head it."""

    source_project_id: int = Field(
        description="The project these bullets belong to, taken from the id given with it."
    )
    title: str = Field(
        description="What the project is, in three to six words of the CV's language that a reader outside the candidate's head would understand, not the name of its folder."
    )
    technologies: list[str] = Field(
        description="The few technologies worth printing beside the title, ordered with the ones the posting asks for first."
    )
    bullets: list[str] = Field(
        description="What the candidate built on this project, one piece of work per bullet, each naming the mechanism that made it work."
    )


class ResumeResponse(BaseModel):
    """What the resume-writing pass returns."""

    summary: list[str] = Field(
        default_factory=list,
        description="One to three short paragraphs placing the candidate against this posting, without naming them.",
    )
    skills: list[ResumeSkillGroup] = Field(
        default_factory=list, description="The skills block, three to six labelled rows."
    )
    work_bullets: list[ResumeWorkBullets] = Field(
        default_factory=list, description="One entry per position given."
    )
    personal_bullets: list[ResumePersonalBullets] = Field(
        default_factory=list, description="One entry per personal project worth showing, at most two."
    )
