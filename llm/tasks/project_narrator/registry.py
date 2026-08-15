# Re-exported rather than reloaded, for the same reason project_tech_identifier
# shares the technology registry: a concept a repo demonstrates and a concept a
# posting demands have to resolve to one DimConcepts row, or the match between
# them means nothing. drop_technologies comes along because the model drops
# product names into the unmatched list here exactly as it does on a posting.
from llm.tasks.concept_identifier.registry import (  # noqa: F401
    NAMES_ONLY,
    NAMES_WITH_ALIASES,
    REGISTRY,
    ConceptName,
    drop_technologies,
)
