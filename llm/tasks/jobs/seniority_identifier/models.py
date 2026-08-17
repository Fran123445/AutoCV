from pydantic import BaseModel, Field

from llm.registries.seniority import SeniorityLabel


# Every field is nullable but none carries a default, so the schema marks all
# four required. A posting with no level still has to come back as an explicit
# null: with defaults the grammar would accept {} and an empty answer would be
# indistinguishable from a considered one.
class Seniority(BaseModel):
    label: SeniorityLabel | None = Field(
        description="The seniority level the posting names for this role, taken verbatim from the allowed list. Null when the posting never names one.",
    )
    min_experience: int | None = Field(
        description="Years of experience the posting demands for the role as a whole. Null when it states none.",
    )
    max_experience: int | None = Field(
        description="Upper bound of years for the role as a whole. Null when the posting states none, meaning there is no upper limit.",
    )
    evidence: str | None = Field(
        description="The phrase from the job description the level was read from, copied verbatim. Null when the posting names no level.",
    )
