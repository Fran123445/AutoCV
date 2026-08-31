"""Task-level requirements for LLM calls."""

from dataclasses import dataclass
from typing import Literal


ReasoningEffort = Literal["none", "low", "medium", "high"]


@dataclass(frozen=True)
class TaskPolicy:
    """Requirements for one task, independent of the provider."""

    name: str
    reasoning_effort: ReasoningEffort
    temperature: float
    zero_data_retention: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("TaskPolicy.name cannot be empty")
        if self.reasoning_effort not in {"none", "low", "medium", "high"}:
            raise ValueError(
                f"Unsupported reasoning effort: {self.reasoning_effort!r}"
            )
