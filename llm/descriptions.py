"""
The response model the describe passes share.

Two pipelines ask the same question of different evidence — a source sample
for projects, the candidate's own account for experience — but the shape of
the answer, and the trick that makes it safe, is identical: only names the
earlier passes found are representable, so a description can't invent a
technology or rename one that was used. Lives here rather than in either task
package because it belongs to neither pipeline, the same reason the
registries do.
"""

from typing import Literal

from pydantic import BaseModel, Field, create_model


# Built per call rather than declared once, because the names allowed here are
# not a registry: they are what the earlier passes found in this one project.


def _entry_model(kind: str, names: list[str]) -> type[BaseModel]:
    """
    Build the entry model for one kind of item, constrained to given names.

    Args:
        kind (str): "Technology" or "Concept", used to name the model.
        names (list[str]): The names this entry is allowed to carry.

    Returns:
        type[BaseModel]: A model with a constrained name and a nullable descr.
    """
    return create_model(
        f"{kind}Description",
        name=(
            Literal[tuple(names)],
            Field(description=f"The {kind.lower()}, taken verbatim from the list given."),
        ),
        descr=(
            str | None,
            Field(
                default=None,
                description="One short phrase naming the part this plays in the project, or null when the source does not show how it is used.",
            ),
        ),
    )


def build_description_model(
    technologies: list[str], concepts: list[str]
) -> type[BaseModel]:
    """
    Build the response model for one project's descriptions.

    Only the kinds that have something to describe get a field, so the grammar
    never offers the model an empty list to populate.

    Args:
        technologies (list[str]): Canonical names from the technology pass.
        concepts (list[str]): Canonical names from the narrative pass.

    Returns:
        type[BaseModel]: A model carrying the description lists.
    """
    fields = {}
    if technologies:
        fields["technologies"] = (
            list[_entry_model("Technology", technologies)],
            Field(description="One entry per technology given, in the same order."),
        )
    if concepts:
        fields["concepts"] = (
            list[_entry_model("Concept", concepts)],
            Field(description="One entry per concept given, in the same order."),
        )

    return create_model("ProjectDescriptions", **fields)
