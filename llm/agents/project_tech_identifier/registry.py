# Re-exported rather than reloaded: this agent reads the same technologies seed
# as tech_identifier, so a second copy would be the same rows under a second
# Literal. Sharing the module is what keeps a repo and a posting resolving
# "react" to one DimTechnologies row. Every other agent's registry loads its own
# seed, which is why the relative-import shape is preserved here.
from llm.agents.tech_identifier.registry import (  # noqa: F401
    NAMES_ONLY,
    NAMES_WITH_ALIASES,
    REGISTRY,
    TECHNOLOGY_NAMES,
    TechnologyName,
)
