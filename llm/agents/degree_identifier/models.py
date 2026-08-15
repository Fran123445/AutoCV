from pydantic import BaseModel, Field

from .registry import DegreeName


# One matched alternative. Both fields required and non-null: a degree only
# lands in the list because the posting named it, so there is always a name and
# always a phrase it was read from.
class Degree(BaseModel):
    name: DegreeName = Field(
        description="An acceptable field of study, taken verbatim from the allowed list.",
    )
    evidence: str = Field(
        description="The phrase from the description this field was read from, copied verbatim.",
    )


# A posting lists degrees as alternatives, so this is a set of acceptable
# fields, not a single answer. Both lists required so an empty answer is an
# explicit [] rather than an omission: a posting that asks for no degree comes
# back with both lists empty, which is different from one the model skipped.
class DegreeRequirement(BaseModel):
    degrees: list[Degree] = Field(
        description="Every field of study the posting accepts, one entry per allowed-list match. Empty when the posting requires no degree.",
    )
    unmatched: list[str] = Field(
        description="Required fields of study, in the posting's own words, that no entry in the allowed list fits. Empty when every named field matched or none was named.",
    )
