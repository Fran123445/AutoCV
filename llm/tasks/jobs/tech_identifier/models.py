from pydantic import BaseModel, Field

from llm.registries.technologies import TechnologyName


class Technology(BaseModel):
    name: TechnologyName = Field(
        description="The name of the technology, taken verbatim from the allowed list."
    )
    min_experience: int | None = Field(
        default=None,
        description="Years of experience required for this specific technology. Null when the job description does not state it.",
    )
    max_experience: int | None = Field(
        default=None,
        description="Upper bound of years for this specific technology. Null when the job description does not state it, meaning there is no upper limit.",
    )


class TechnologyList(BaseModel):
    required_technologies: list[Technology] = Field(
        description="The technologies the job description demands."
    )
    nice_to_have_technologies: list[Technology] = Field(
        description="The technologies the job description treats as desirable rather than required."
    )
    discarded_technologies: list[str] = Field(
        description="Technologies mentioned in the job description but not available as an option."
    )


class SecondPassResult(BaseModel):
    missed_required_technologies: list[Technology] = Field(
        description="Required technologies the first pass failed to report."
    )
    missed_nice_to_have_technologies: list[Technology] = Field(
        description="Nice-to-have technologies the first pass failed to report."
    )
    resolved_terms: list[str] = Field(
        description="Entries from the unmatched list that turned out to be a technology in the allowed list, copied verbatim."
    )
