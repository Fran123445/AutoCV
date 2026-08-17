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
