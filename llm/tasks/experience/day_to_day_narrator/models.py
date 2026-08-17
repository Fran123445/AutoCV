from pydantic import BaseModel, Field

from llm.registries.concepts import ConceptName


class DayToDayNarrative(BaseModel):
    """
    What FactExperience.day_to_day is written from.

    Shaped like the projects side's ProjectNarrative and for the same reason:
    the prose loads a column the CV generator reads, the concepts are evidence
    tags on the same reading, and one pass over the account answers both.

    The prose is the half that matters most here. A job with no Project block
    behind it reaches the generator as a role, a company and a set of tags, and
    tags are enough to match a posting but not enough to write a line about.
    """

    day_to_day: str = Field(
        description="What the job consisted of day to day, in three to five sentences, in English and in the third person, without naming the company."
    )
    concepts: list[ConceptName] = Field(
        description="The concepts the account shows the candidate practising, taken verbatim from the allowed list."
    )
    discarded_concepts: list[str] = Field(
        description="Concepts the account demonstrates that have no match in the allowed list."
    )
