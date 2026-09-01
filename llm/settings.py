"""Configuration for one LLM client.

The application may run several pipelines against different models.  Settings
therefore belong to a client instance rather than to module-level constants.
Environment variables provide the defaults and may be prefixed with a
pipeline name, for example ``AUTOCV_JOBS_MODEL_NAME``.
"""

from dataclasses import dataclass
import os
from typing import Literal, cast

from config import ROOT_DIR  # importing config also loads the project's .env
from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")


ProviderName = Literal["llama-server", "openrouter"]


def _env(name: str, fallback: str, pipeline: str | None) -> str:
    if pipeline:
        value = os.getenv(f"AUTOCV_{pipeline.upper()}_{name}")
        if value not in (None, ""):
            return value
    return os.getenv(f"AUTOCV_{name}") or fallback


@dataclass(frozen=True)
class LLMSettings:
    """All runtime settings needed by one LLM client."""

    base_url: str
    chat_completions_path: str
    api_key: str
    model_name: str
    timeout: float
    max_concurrency: int
    provider: ProviderName = "llama-server"

    @classmethod
    def from_env(cls, pipeline: str) -> "LLMSettings":
        """Load settings, preferring values specific to ``pipeline``."""
        provider = _env("PROVIDER", "llama-server", pipeline)
        if provider not in {"llama-server", "openrouter"}:
            raise ValueError(
                "AUTOCV_PROVIDER must be 'llama-server' or 'openrouter'"
            )

        return cls(
            provider=cast(ProviderName, provider),
            base_url=_env("BASE_URL", "http://localhost:5001", pipeline),
            chat_completions_path="/v1/chat/completions",
            api_key=_env("API_KEY", "", pipeline),
            model_name=_env("MODEL_NAME", "", pipeline),
            timeout=float(_env("TIMEOUT", "300", pipeline)),
            max_concurrency=int(_env("MAX_CONCURRENCY", "4", pipeline)),
        )

    def snapshot(self) -> dict:
        """Return non-secret settings suitable for run telemetry."""
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model_name": self.model_name,
            "timeout": self.timeout,
            "max_concurrency": self.max_concurrency,
        }
