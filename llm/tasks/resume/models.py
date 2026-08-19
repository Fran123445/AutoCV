"""Structured context passed to the resume-writing LLM."""

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


class ResumePromptProject(_PromptBlock):
    """One project supplied as context to the LLM."""

    source_project_id: int
    description: str
    source_experience_id: int | None = None
    technologies: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)


class ResumePromptContext(_PromptBlock):
    """Structured candidate and job data rendered into an LLM prompt."""

    job_description: str
    profile: ResumeProfile
    education: list[ResumeEducation] = Field(default_factory=list)
    experience: list[ResumePromptExperience] = Field(default_factory=list)
    work_projects: list[ResumePromptProject] = Field(default_factory=list)
    personal_projects: list[ResumePromptProject] = Field(default_factory=list)
