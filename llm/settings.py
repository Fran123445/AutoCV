"""Configuration for one LLM client.

The application may run several pipelines against different models.  Settings
therefore belong to a client instance rather than to module-level constants.
Environment variables provide the defaults and may be prefixed with a
pipeline name, for example ``AUTOCV_JOBS_MODEL_NAME``.
"""

from dataclasses import dataclass, field
import os
from typing import Mapping

from config import ROOT_DIR  # importing config also loads the project's .env
from dotenv import load_dotenv


load_dotenv(ROOT_DIR / ".env")


REASONING_EFFORT_BY_TASK = {
    "resume.write": "low",
    "experience.tech_identifier.day_to_day": "low",
    "experience.tech_identifier.project": "low",
    "experience.project_describer.describe": "low",
    "experience.project_narrator.narrate": "low",
    "experience.day_to_day_narrator.narrate": "low",
    "jobs.tech_identifier.first_pass": "low",
    "jobs.tech_identifier.second_pass": "low",
    "jobs.concept_identifier.first_pass": "low",
    "jobs.concept_identifier.second_pass": "low",
    "projects.analyzer.analyze": "low",
    "jobs.role_identifier.classify": "none",
    "jobs.seniority_identifier.classify": "none",
    "jobs.degree_identifier.classify": "none",
}


def _env(name: str, fallback: str, pipeline: str | None) -> str:
    if pipeline:
        value = os.getenv(f"AUTOCV_{pipeline.upper()}_{name}")
        if value not in (None, ""):
            return value
    return os.getenv(f"AUTOCV_{name}") or fallback


@dataclass(frozen=True)
class LLMSettings:
    """All runtime settings needed by one OpenAI-compatible LLM client."""

    base_url: str
    chat_completions_path: str
    api_key: str
    model_name: str
    timeout: float
    temperature: float
    max_concurrency: int
    reasoning_effort_by_task: Mapping[str, str] = field(
        default_factory=lambda: dict(REASONING_EFFORT_BY_TASK)
    )

    @classmethod
    def from_env(cls, pipeline: str) -> "LLMSettings":
        """Load settings, preferring values specific to ``pipeline``."""
        return cls(
            base_url=_env("BASE_URL", "http://localhost:5001", pipeline),
            chat_completions_path="/v1/chat/completions",
            api_key=_env("API_KEY", "", pipeline),
            model_name=_env("MODEL_NAME", "", pipeline),
            timeout=float(_env("TIMEOUT", "300", pipeline)),
            temperature=float(_env("TEMPERATURE", "1", pipeline)),
            max_concurrency=int(_env("MAX_CONCURRENCY", "4", pipeline)),
        )

    def snapshot(self) -> dict:
        """Return non-secret settings suitable for run telemetry."""
        return {
            "base_url": self.base_url,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "timeout": self.timeout,
            "max_concurrency": self.max_concurrency,
        }
