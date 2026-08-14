from typing import Literal

from llm.seeds import load_seed, render_with_aliases


REGISTRY = load_seed("seniority.json", "seniorities")
SENIORITY_LABELS = [seniority["label"] for seniority in REGISTRY]

# Constrained decoding turns this into a grammar, so a label outside the
# registry becomes unrepresentable rather than merely discouraged.
SeniorityLabel = Literal[tuple(SENIORITY_LABELS)]

# A single pass, so the aliases go in from the start: there is no review pass
# here to widen the vocabulary on a second look.
LABELS_WITH_ALIASES = render_with_aliases(REGISTRY, key="label")

# Years a label typically implies. Not sent to the model, which reports the
# years a posting states and leaves the label alone: mapping years to a label
# belongs to the load stage, where it is deterministic.
TYPICAL_YEARS = {
    seniority["label"]: (seniority["typical_min_exp"], seniority["typical_max_exp"])
    for seniority in REGISTRY
}
