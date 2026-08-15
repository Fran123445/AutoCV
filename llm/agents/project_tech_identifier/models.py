from pydantic import BaseModel, Field

from .registry import TechnologyName


class ProjectTechnologyList(BaseModel):
    """
    Flat by design, unlike the job side's TechnologyList.

    A posting splits its technologies into required and nice-to-have and may put
    years on each one. A repository has neither axis: the code either uses a
    technology or it does not. How a technology was used is a separate question,
    answered by the sampling pass that fills ProjectTechnologies.descr, since
    manifests and file names show which technology is present but never why.
    """

    technologies: list[TechnologyName] = Field(
        description="The technologies the project uses, taken verbatim from the allowed list."
    )
    discarded_technologies: list[str] = Field(
        description="Dependencies or tools seen in the project but with no match in the allowed list."
    )


class SecondPassResult(BaseModel):
    missed_technologies: list[TechnologyName] = Field(
        description="Technologies the first pass failed to report."
    )
    resolved_terms: list[str] = Field(
        description="Entries from the unmatched list that turned out to be a technology in the allowed list, copied verbatim."
    )
