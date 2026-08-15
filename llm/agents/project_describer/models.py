from typing import Literal

from pydantic import BaseModel, Field, create_model


# Built per call rather than declared once, because the names allowed here are
# not a registry: they are what the earlier passes found in this one project.
# Constraining to those is what stops the model from describing a technology the
# project does not use, or from renaming one it does.


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
