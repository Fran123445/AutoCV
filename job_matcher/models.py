from pydantic import BaseModel, ConfigDict, Field


class EvidenceTag(BaseModel):
    """A technology or concept reached from a project's direct tags."""

    model_config = ConfigDict(extra="forbid")

    id: int
    # Zero means that the project was tagged with this dimension directly.
    # Larger values mean that it was reached by walking dependency edges.
    depth: int = Field(ge=0)


class ProjectEvidence(BaseModel):
    """The skills and concepts a project can provide evidence for."""

    model_config = ConfigDict(extra="forbid")

    id: int
    experience_id: int | None = None

    technologies: list[EvidenceTag] = Field(default_factory=list)
    concepts: list[EvidenceTag] = Field(default_factory=list)
