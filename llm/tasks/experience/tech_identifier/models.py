from pydantic import BaseModel, Field

from llm.registries.technologies import TechnologyName


class ExperienceTechnologyList(BaseModel):
    """
    Flat like the projects side, unlike the job side's TechnologyList.

    A posting splits its technologies into required and nice-to-have and may put
    years on each one. A job somebody held has neither axis: they worked with a
    technology or they did not. Years are not per technology here either, since
    the job's own start and end dates already say how long, and they are on the
    block in the file rather than in the prose.
    """

    technologies: list[TechnologyName] = Field(
        description="The technologies the account shows the candidate working with, taken verbatim from the allowed list."
    )
    discarded_technologies: list[str] = Field(
        description="Technologies the account names as the candidate's own work but with no match in the allowed list."
    )
