import json
import time

import httpx

from run_log import LLMCall, prompt_fingerprint, record_call, utc_now

from llm.settings import LLMSettings


class LLMClient:
    """Thread-safe client for one OpenAI-compatible chat-completions target."""

    def __init__(self, settings: LLMSettings):
        self.settings = settings
        # One client is shared by all workers in the pipeline. httpx.Client is
        # thread-safe and reuses connections, while each LLMClient can target a
        # different model or endpoint.
        self._http = httpx.Client(
            base_url=settings.base_url,
            timeout=settings.timeout,
            limits=httpx.Limits(max_connections=settings.max_concurrency),
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
        task_name: str = "unknown",
        reasoning_effort: str | None = None,
    ) -> dict:
        """Send a prompt to this client's model and return parsed JSON.

        The call is also attached to the current run item by ``run_log``.
        """
        effort = reasoning_effort or self.settings.reasoning_effort_by_task[task_name]

        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "autocv_response",
                    "strict": True,
                    "schema": schema,
                },
            },
            "temperature": self.settings.temperature,
            "reasoning_effort": effort,
        }
        is_openrouter = "openrouter.ai" in self.settings.base_url.lower()

        if effort == "none" and not is_openrouter:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        # OpenRouter can route a model to endpoints that do not support every
        # parameter in the request unless this is explicitly required.
        if is_openrouter:
            payload["provider"] = {"require_parameters": True}

        if self.settings.model_name:
            payload["model"] = self.settings.model_name

        headers = (
            {"Authorization": f"Bearer {self.settings.api_key}"}
            if self.settings.api_key
            else None
        )

        call = LLMCall(
            task_name=task_name,
            started_at=utc_now(),
            temperature=self.settings.temperature,
            reasoning_effort=effort,
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
