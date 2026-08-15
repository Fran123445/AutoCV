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

# Read straight from the seed rather than through the technology task: both
# registries are just files, and going through the task would couple the two
# for nothing.
TECHNOLOGY_SURFACES = {
    surface.casefold()
    for tech in load_seed("technologies.json", "technologies")
    for surface in (tech["name"], *tech["aliases"])
}


# Postings name a product and then say what it is: "PI historian technology".
# Stripping the trailing noun catches those. Matching on substrings instead
# would be far worse, since short names like "go" or "c" sit inside ordinary
# words such as "data governance".
_TRAILING_NOUNS = (
    " technology",
    " technologies",
    " platform",
    " platforms",
    " tool",
    " tools",
)


def _normalise(term: str) -> str:
    """
    Casefold a term and drop a trailing generic noun, if it carries one.

    Args:
        term (str): Term as the model reported it.
    """
    normalised = term.casefold().strip()
    for noun in _TRAILING_NOUNS:
        if normalised.endswith(noun):
            return normalised[: -len(noun)].strip()

    return normalised


def drop_technologies(terms: list[str]) -> list[str]:
    """
    Remove technology names from a list of unmatched terms.

    The two concept lists are constrained by the grammar, so nothing outside
    the registry can reach them. The unmatched list is free text, and the model
    does drop product names into it however plainly the prompt says not to.

    Args:
        terms (list[str]): Terms the model reported as unmatched.
    """
    return [term for term in terms if _normalise(term) not in TECHNOLOGY_SURFACES]
