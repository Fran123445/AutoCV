"""Task-level requirements for LLM calls.

Policies live here rather than beside every prompt so task modules only need to
name the work they are doing.  This keeps provider- and model-specific choices
auditable in one place.
"""

from dataclasses import dataclass
from typing import Literal


ReasoningEffort = Literal["none", "low", "medium", "high"]


@dataclass(frozen=True)
class TaskPolicy:
    """Requirements for one task, independent of the provider."""

    reasoning_effort: ReasoningEffort = "low"
    temperature: float = 0.0
    zero_data_retention: bool = False

    def __post_init__(self) -> None:
        if self.reasoning_effort not in {"none", "low", "medium", "high"}:
            raise ValueError(
                f"Unsupported reasoning effort: {self.reasoning_effort!r}"
            )
        if not 0 <= self.temperature <= 2:
            raise ValueError("TaskPolicy.temperature must be between 0 and 2")


# Shared profiles make the intent of each entry obvious and avoid a long list
# of near-identical settings.
FAST_EXTRACT = TaskPolicy(reasoning_effort="low")
EXTRACT = TaskPolicy(reasoning_effort="low")
REVIEW = TaskPolicy(reasoning_effort="low")
PRIVATE_EXTRACT = TaskPolicy(reasoning_effort="low", zero_data_retention=True)
PRIVATE_NARRATION = TaskPolicy(reasoning_effort="low", zero_data_retention=True)
PRIVATE_ANALYSIS = TaskPolicy(reasoning_effort="low", zero_data_retention=True)
PRIVATE_WRITING = TaskPolicy(
    reasoning_effort="medium",
    zero_data_retention=True,
)


POLICIES: dict[str, TaskPolicy] = {
    "jobs.tech_identifier.first_pass": EXTRACT,
    "jobs.tech_identifier.second_pass": REVIEW,
    "jobs.concept_identifier.first_pass": EXTRACT,
    "jobs.concept_identifier.second_pass": REVIEW,
    "jobs.role_identifier.classify": FAST_EXTRACT,
    "jobs.seniority_identifier.classify": FAST_EXTRACT,
    "jobs.degree_identifier.classify": FAST_EXTRACT,
    "experience.tech_identifier.day_to_day": PRIVATE_EXTRACT,
    "experience.tech_identifier.project": PRIVATE_EXTRACT,
    "experience.day_to_day_narrator.narrate": PRIVATE_NARRATION,
    "experience.project_describer.describe": PRIVATE_NARRATION,
    "experience.project_narrator.narrate": PRIVATE_NARRATION,
    "projects.analyzer.analyze": PRIVATE_ANALYSIS,
    "resume.write": PRIVATE_WRITING,
}


def policy_for(task_name: str) -> TaskPolicy:
    """Return the policy registered for a named task.

    Requiring every task to be registered prevents a new prompt from silently
    inheriting an arbitrary provider default.
    """
    try:
        return POLICIES[task_name]
    except KeyError as exc:
        raise ValueError(f"No LLM policy registered for task {task_name!r}") from exc
