"""Intermediate representation for generated resumes.

The models in this module describe a resume after evidence has been selected
and before a renderer turns it into HTML, PDF, or another artifact.  They are
deliberately independent from the database schema and from any one template.

Every field here is one a renderer prints or keys on.  What the pipeline used
to reach a field — the tags behind a bullet, the taxonomy name for a position,
the id of the block in experience.toml — stays on the database and on the
prompt models, since a document carrying it would only invite a template to
print it.
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


class ResumeSkillGroup(_ResumeBlock):
    """One labelled row of the skills block."""

    label: str
    items: list[str] = Field(default_factory=list)


class ResumeProject(_ResumeBlock):
    """A personal project selected for this resume."""

    title: str
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    source_project_id: int | None = None


class ResumeExperience(_ResumeBlock):
    """One position in the candidate's work history."""

    company: str
    role: str
    job_title: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    bullets: list[str] = Field(default_factory=list)
    source_experience_id: int | None = None


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
    summary: list[str] = Field(default_factory=list)
    skills: list[ResumeSkillGroup] = Field(default_factory=list)
    experience: list[ResumeExperience] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    education: list[ResumeEducation] = Field(default_factory=list)
    languages: list[ResumeLanguage] = Field(default_factory=list)
