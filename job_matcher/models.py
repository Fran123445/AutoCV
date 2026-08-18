from pydantic import BaseModel, ConfigDict, Field


class JobPosting(BaseModel):
    """One row of FactJob with its tagged technologies and concepts."""

    model_config = ConfigDict(extra="forbid")

    id: int

    company_name: str | None = None
    position_name: str | None = None
    typical_min_exp: int | None = None

    required_technology_ids: set[int] = Field(default_factory=set)
    optional_technology_ids: set[int] = Field(default_factory=set)
    required_concept_ids: set[int] = Field(default_factory=set)
    optional_concept_ids: set[int] = Field(default_factory=set)
