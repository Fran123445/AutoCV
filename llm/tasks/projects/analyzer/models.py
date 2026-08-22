"""Structured response returned by the whole-repository project analyzer."""

from pydantic import BaseModel, Field

from llm.registries.concepts import ConceptName
from llm.registries.technologies import TechnologyName


class TechnologyEntry(BaseModel):
    name: TechnologyName = Field(
        description="A technology, verbatim from the allowed list."
    )
    descr: str | None = Field(
        default=None,
        description="Two or three sentences on the part it plays in the project and how it is used, or null when the code does not show it in use.",
    )


class ConceptEntry(BaseModel):
    name: ConceptName = Field(
        description="A concept, verbatim from the allowed list."
    )
    descr: str | None = Field(
        default=None,
        description="Two or three sentences on how the project demonstrates it, or null when the code does not show it.",
    )


class RepoAnalysis(BaseModel):
    """The whole pipeline's answer folded into one call's response."""

    task_desc: str = Field(
        description="What the project is and does, in two or three sentences, third person, without naming the project."
    )
    technologies: list[TechnologyEntry] = Field(
        description="Every technology the project uses, each with its role."
    )
    concepts: list[ConceptEntry] = Field(
        description="Every concept the project demonstrates, each with how it shows up."
    )
    discarded_technologies: list[str] = Field(
        description="Dependencies or tools clearly present but absent from the allowed list."
    )
    discarded_concepts: list[str] = Field(
        description="Concepts clearly demonstrated but absent from the allowed list."
    )
