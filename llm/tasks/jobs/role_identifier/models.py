from pydantic import BaseModel, Field

from llm.registries.roles import RoleName


# Every field is nullable but none carries a default, so the schema marks all
# three required. A posting with no recognisable role still has to come back as
# an explicit null: with defaults the grammar would accept {} and an empty
# answer would be indistinguishable from a considered one.
class Role(BaseModel):
    name: RoleName | None = Field(
        description="The role the posting advertises, taken verbatim from the allowed list. Null when no entry in the list fits.",
    )
    evidence: str | None = Field(
        description="The phrase from the title or description the role was read from, copied verbatim. Null when no role was identified.",
    )
    unmatched: str | None = Field(
        description="The role the posting advertises, in its own words, when no entry in the allowed list fits. Null whenever name is filled.",
    )
