import json
from typing import Literal

from llm.config import SEEDS_DIR


SEEDS_PATH = SEEDS_DIR / "technologies.json"


def _load_registry() -> list[dict]:
    """
    Load the technology registry
    """
    with open(SEEDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["technologies"]


REGISTRY = _load_registry()
TECHNOLOGY_NAMES = [tech["name"] for tech in REGISTRY]

# Constrained decoding turns this into a grammar, so a name outside the
# registry becomes unrepresentable rather than merely discouraged.
TechnologyName = Literal[tuple(TECHNOLOGY_NAMES)]


def _render_with_aliases() -> str:
    """
    Render the registry as "canonical (alias, alias)" entries.
    """
    entries = []
    for tech in REGISTRY:
        if tech["aliases"]:
            entries.append(f"{tech['name']} ({', '.join(tech['aliases'])})")
        else:
            entries.append(tech["name"])

    return ", ".join(entries)


# The first pass only ever sees canonical names, which is why terms like
# "spark" or "pi historian" end up unmatched. The review pass gets the aliases
# too, so it can bridge a term in the posting to the name in the registry.
NAMES_ONLY = ", ".join(TECHNOLOGY_NAMES)
NAMES_WITH_ALIASES = _render_with_aliases()
