from typing import Literal

from llm.seeds import load_seed, render_names, render_with_aliases


REGISTRY = load_seed("technologies.json", "technologies")
TECHNOLOGY_NAMES = [tech["name"] for tech in REGISTRY]

# Constrained decoding turns this into a grammar, so a name outside the
# registry becomes unrepresentable rather than merely discouraged.
TechnologyName = Literal[tuple(TECHNOLOGY_NAMES)]

# The first pass only ever sees canonical names, which is why terms like
# "spark" or "pi historian" end up unmatched. The review pass gets the aliases
# too, so it can bridge a term in the posting to the name in the registry.
NAMES_ONLY = render_names(REGISTRY)
NAMES_WITH_ALIASES = render_with_aliases(REGISTRY)

# Every spelling of a technology mapped back to its canonical name, so an
# import of "torch" can be recognised as the evidence behind "pytorch". One
# table for every caller that has to go from a surface to a row: the sampler
# resolving module names and the unmatched-list cleanup below both read it, and
# building it twice is how the two would start disagreeing about "torch".
SURFACE_TO_NAME = {
    surface.casefold(): technology["name"]
    for technology in REGISTRY
    for surface in (technology["name"], *technology["aliases"])
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

    Lives with the technologies rather than beside the concept tasks that call
    it, because technology surfaces are all it knows. The concept lists proper
    are constrained by the grammar, so nothing outside that registry can reach
    them; it is the free-text unmatched list that collects product names
    however plainly the prompt says not to.

    Args:
        terms (list[str]): Terms the model reported as unmatched.
    """
    return [term for term in terms if _normalise(term) not in SURFACE_TO_NAME]
