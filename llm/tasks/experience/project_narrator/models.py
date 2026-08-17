from pydantic import BaseModel, Field

from llm.registries.concepts import ConceptName


class JobProjectNarrative(BaseModel):
    """
    What a Project row born of a job gets written from.

    Same three fields as the projects side's ProjectNarrative, and a different
    thing underneath: that one is read off a repository, so its task_desc is
    the model's reading of code nobody described. This one is read off the
    candidate's own telling, so its task_desc is their claim, trimmed to their
    share of the work. task_desc loads a NOT NULL column either way and is the
    one field that must always come back with something.
    """

    task_desc: str = Field(
        description="What the project was and what the candidate did on it, in three or four sentences, in English and in the third person, without naming the project."
    )
    concepts: list[ConceptName] = Field(
        description="The concepts the account shows the candidate practising on this project, taken verbatim from the allowed list."
    )
    discarded_concepts: list[str] = Field(
        description="Concepts the project demonstrates that have no match in the allowed list."
    )
