import json
import time
from typing import Any, Literal

import httpx

from run_log import LLMCall, prompt_fingerprint, record_call, utc_now

from llm.policy import TaskPolicy
from llm.settings import LLMSettings


ProviderName = Literal["llama-server", "openrouter"]


class LLMClient:
    """Thread-safe client for one provider target."""

    def __init__(
        self,
        settings: LLMSettings,
        provider: ProviderName,
        transport: httpx.BaseTransport | None = None,
    ):
        self.settings = settings
        self.provider = provider
        # One client is shared by all workers in the pipeline. httpx.Client is
        # thread-safe and reuses connections, while each LLMClient can target a
        # different model or endpoint.
        self._http = httpx.Client(
            base_url=settings.base_url,
            timeout=settings.timeout,
            limits=httpx.Limits(max_connections=settings.max_concurrency),
            transport=transport,
        )

    def close(self):
        """Close the underlying connection pool."""
        self._http.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def post_chat(
        self,
        prompt: str,
        schema: dict,
        *,
        policy: TaskPolicy,
    ) -> dict:
        """Send a prompt to this client's model and return parsed JSON.

        The call is also attached to the current run item by ``run_log``.
        The policy is required so task-specific model requirements are explicit
        at every call site.
        """
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "autocv_response",
                    "strict": True,
                    "schema": schema,
                },
            },
            "temperature": policy.temperature,
            "reasoning_effort": policy.reasoning_effort,
        }
        if self.settings.model_name:
            payload["model"] = self.settings.model_name

        if self.provider == "llama-server" and policy.reasoning_effort == "none":
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        elif self.provider == "openrouter":
            provider_options: dict[str, Any] = {"require_parameters": True}
            if policy.zero_data_retention is True:
                provider_options["zdr"] = True
            payload["provider"] = provider_options

        headers = (
            {"Authorization": f"Bearer {self.settings.api_key}"}
            if self.settings.api_key
            else None
        )

        call = LLMCall(
            task_name=policy.name,
            started_at=utc_now(),
            temperature=policy.temperature,
            reasoning_effort=policy.reasoning_effort,
            prompt_sha1=prompt_fingerprint(prompt),
        )
        started = time.perf_counter()
        response = None

        try:
            response = self._http.post(
                self.settings.chat_completions_path,
                json=payload,
                headers=headers,
            )
            call.http_status = response.status_code

            body = response.json()
            usage = body.get("usage") or {}
            call.prompt_tokens = usage.get("prompt_tokens")
            call.completion_tokens = usage.get("completion_tokens")
            call.model_name = body.get("model")

            content = body["choices"][0]["message"]["content"].strip()
            if content.startswith("```") and content.endswith("```"):
                lines = content.splitlines()
                if lines and lines[0].strip().lower() in {"```", "```json"}:
                    content = "\n".join(lines[1:-1]).strip()
            content = json.loads(content)
        except Exception as e:
            call.status = "failed"
            call.error = repr(e)
            raise ValueError(
                f"Failed to parse response: {e}. Response content: "
                f"{response.text if response is not None else '(no response)'}"
            )
        else:
            call.status = "completed"
            return content
        finally:
            call.ended_at = utc_now()
            call.latency_ms = int((time.perf_counter() - started) * 1000)
            record_call(call)
