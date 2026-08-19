"""Structured context passed to the resume-writing LLM, and what it returns."""

from pydantic import BaseModel, ConfigDict, Field

from resume_generator.models import ResumeEducation, ResumeProfile


class _PromptBlock(BaseModel):
    """Common validation policy for LLM prompt data."""

    model_config = ConfigDict(extra="forbid")


class ResumePromptExperience(_PromptBlock):
    """One work-history entry supplied as context to the LLM."""

    source_experience_id: int
    company: str
    role: str
    seniority: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    day_to_day: str | None = None


class ResumePromptTag(_PromptBlock):
    """One technology or concept a project is evidence for."""

    name: str
    descr: str | None = None


class ResumePromptProject(_PromptBlock):
    """One project supplied as context to the LLM."""

    source_project_id: int
    description: str
    source_experience_id: int | None = None
    technologies: list[ResumePromptTag] = Field(default_factory=list)
    concepts: list[ResumePromptTag] = Field(default_factory=list)


class ResumePromptContext(_PromptBlock):
    """Structured candidate and job data rendered into an LLM prompt."""

    job_description: str
    profile: ResumeProfile
    education: list[ResumeEducation] = Field(default_factory=list)
    experience: list[ResumePromptExperience] = Field(default_factory=list)
    work_projects: list[ResumePromptProject] = Field(default_factory=list)
    personal_projects: list[ResumePromptProject] = Field(default_factory=list)


class ResumeWorkBullets(BaseModel):
    """The bullets written for one position in the work history."""

    source_experience_id: int = Field(
        description="The position these bullets belong to, taken from the id given with it."
    )
    bullets: list[str] = Field(
        description="What the candidate did in this position, one claim per bullet, in English and in the third person."
    )


class ResumePersonalBullets(BaseModel):
    """The bullets written for one personal project."""

    source_project_id: int = Field(
        description="The project these bullets belong to, taken from the id given with it."
    )
    bullets: list[str] = Field(
        description="What the project is and what the candidate built on it, one claim per bullet, in English and in the third person."
    )


class ResumeResponse(BaseModel):
    """What the resume-writing pass returns."""

    summary: str = Field(
        description="The candidate's fit for the job description, in three or four sentences, in English and in the third person, without naming the candidate."
    )
    work_bullets: list[ResumeWorkBullets] = Field(
        default_factory=list, description="One entry per position given."
    )
    personal_bullets: list[ResumePersonalBullets] = Field(
        default_factory=list, description="One entry per personal project given."
    )
