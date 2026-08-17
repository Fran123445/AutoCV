from pydantic import BaseModel, Field

from llm.registries.concepts import ConceptName


class ProjectNarrative(BaseModel):
    """
    What the resume module is eventually written from.

    task_desc is the project's own story and loads a NOT NULL column, so it is
    the one field here that must always come back with something. The concepts
    are evidence tags on the same reading, which is why they share a call: the
    same pass over the source answers both, and splitting them would pay twice
    for one read.
    """

    task_desc: str = Field(
        description="What the project is and what it does, in two or three sentences. States the problem it solves and how it is built, in the third person, without naming the project."
    )
    concepts: list[ConceptName] = Field(
        description="The concepts the project demonstrates, taken verbatim from the allowed list."
    )
    discarded_concepts: list[str] = Field(
        description="Concepts the project demonstrates that have no match in the allowed list."
    )
