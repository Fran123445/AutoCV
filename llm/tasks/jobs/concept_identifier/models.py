from pydantic import BaseModel, Field

from llm.registries.concepts import ConceptName


class Concept(BaseModel):
    name: ConceptName = Field(
        description="The name of the concept, taken verbatim from the allowed list."
    )
    min_experience: int | None = Field(
        default=None,
        description="Years of experience required for this specific concept. Null when the job description does not state it.",
    )
    max_experience: int | None = Field(
        default=None,
        description="Upper bound of years for this specific concept. Null when the job description does not state it, meaning there is no upper limit.",
    )


class ConceptList(BaseModel):
    required_concepts: list[Concept] = Field(
        description="The concepts the job description demands."
    )
    nice_to_have_concepts: list[Concept] = Field(
        description="The concepts the job description treats as desirable rather than required."
    )
    discarded_concepts: list[str] = Field(
        description="Concepts mentioned in the job description but not available as an option."
    )


class SecondPassResult(BaseModel):
    missed_required_concepts: list[Concept] = Field(
        description="Required concepts the first pass failed to report."
    )
    missed_nice_to_have_concepts: list[Concept] = Field(
        description="Nice-to-have concepts the first pass failed to report."
    )
    resolved_terms: list[str] = Field(
        description="Entries from the unmatched list that turned out to be a concept in the allowed list, copied verbatim."
    )
