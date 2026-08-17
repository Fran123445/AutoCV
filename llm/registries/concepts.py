from typing import Literal

from llm.seeds import load_seed, render_names, render_with_aliases


REGISTRY = load_seed("concepts.json", "concepts")
CONCEPT_NAMES = [concept["name"] for concept in REGISTRY]

# Constrained decoding turns this into a grammar, so a name outside the
# registry becomes unrepresentable rather than merely discouraged.
ConceptName = Literal[tuple(CONCEPT_NAMES)]

# The first pass only ever sees canonical names, which is why terms like "rag"
# or "ia generativa" end up unmatched. The review pass gets the aliases too, so
# it can bridge a term in the posting to the name in the registry.
NAMES_ONLY = render_names(REGISTRY)
NAMES_WITH_ALIASES = render_with_aliases(REGISTRY)

# Every spelling of a concept mapped back to its canonical name, the same table
# the technologies registry keeps for the same reason.
SURFACE_TO_NAME = {
    surface.casefold(): concept["name"]
    for concept in REGISTRY
    for surface in (concept["name"], *concept["aliases"])
}


def resolve_concepts(terms: list[str]) -> tuple[list[str], list[str]]:
    """
    Split unmatched terms into the ones the registry does hold and the rest.

    A task that runs one pass has no review behind it to bridge a term, and the
    model does put registry members in its unmatched list: "data pipelines" and
    "elt" have come back as unmatched from a prompt that listed both. Left
    alone they are lost twice over, since they are not in the tagged list
    either, and the terms that survive stop being a signal of what the registry
    is missing. The two-pass tasks get this from resolved_terms and the merge;
    this is the same bridge, drawn from the seed instead of from the model.

    Args:
        terms (list[str]): Terms the model reported as unmatched.

    Returns:
        tuple[list[str], list[str]]: The canonical names recovered, without
            duplicates and in the order they were found, and the terms that
            really have no entry.
    """
    resolved: list[str] = []
    unmatched: list[str] = []

    for term in terms:
        name = SURFACE_TO_NAME.get(term.casefold().strip())
        if name is None:
            unmatched.append(term)
        elif name not in resolved:
            resolved.append(name)

    return resolved, unmatched
