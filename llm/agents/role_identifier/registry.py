from typing import Literal

from llm.seeds import load_seed, render_with_aliases


REGISTRY = load_seed("roles.json", "roles")
ROLE_NAMES = [role["name"] for role in REGISTRY]

# Constrained decoding turns this into a grammar, so a name outside the
# registry becomes unrepresentable rather than merely discouraged.
RoleName = Literal[tuple(ROLE_NAMES)]

# A single pass, so the aliases go in from the start: there is no review pass
# here to widen the vocabulary on a second look.
NAMES_WITH_ALIASES = render_with_aliases(REGISTRY)
