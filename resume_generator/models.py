"""Intermediate representation for generated resumes.

The models in this module describe a resume after evidence has been selected
and before a renderer turns it into HTML, PDF, or another artifact.  They are
deliberately independent from the database schema and from any one template.
"""

from pydantic import BaseModel, ConfigDict, Field


class _ResumeBlock(BaseModel):
    """Common validation policy for resume documents."""

    model_config = ConfigDict(extra="forbid")


class ResumeLink(_ResumeBlock):
    """A contact or portfolio link shown in the resume header."""

    kind: str
    url: str


class ResumeProfile(_ResumeBlock):
    """Candidate information displayed in the resume header."""

    full_name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[ResumeLink] = Field(default_factory=list)


class ResumeLanguage(_ResumeBlock):
    """One spoken language and how well the candidate speaks it."""

    name: str
    level: str | None = None


class ResumeBullet(_ResumeBlock):
    """One resume bullet and the evidence used to produce it."""

    text: str
    source_project_id: int | None = None
    source_experience_id: int | None = None
    technologies: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)


class ResumeProject(_ResumeBlock):
    """A selected project, either personal or attached to a position."""

    title: str | None = None
    description: str
    bullets: list[ResumeBullet] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    source_project_id: int | None = None
    source_experience_id: int | None = None
    source_id: str | None = None


class ResumeExperience(_ResumeBlock):
    """One position in the candidate's work history."""

    company: str
    role: str
    job_title: str | None = None
    seniority: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    bullets: list[ResumeBullet] = Field(default_factory=list)
    source_experience_id: int | None = None
    source_id: str | None = None


class ResumeEducation(_ResumeBlock):
    """One education entry shown in the resume."""

    degree: str
    institution: str | None = None
    gpa: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class ResumeDocument(_ResumeBlock):
    """Complete renderer-independent representation of a generated resume."""

    profile: ResumeProfile
    summary: str | None = None
    experience: list[ResumeExperience] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    education: list[ResumeEducation] = Field(default_factory=list)
    languages: list[ResumeLanguage] = Field(default_factory=list)
