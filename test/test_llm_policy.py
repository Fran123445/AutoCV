import json

import httpx

from llm.client import LLMClient
from llm.policy import policy_for
from llm.settings import LLMSettings


def test_settings_reads_pipeline_provider_override(monkeypatch):
    monkeypatch.setenv("AUTOCV_PROVIDER", "llama-server")
    monkeypatch.setenv("AUTOCV_JOBS_PROVIDER", "openrouter")

    settings = LLMSettings.from_env("jobs")

    assert settings.provider == "openrouter"
    assert settings.snapshot()["provider"] == "openrouter"


def test_client_sends_the_registered_policy_to_openrouter():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = request.read()
        return httpx.Response(
            200,
            json={
                "model": "served-model",
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                "choices": [{"message": {"content": '{"ok": true}'}}],
            },
        )

    settings = LLMSettings(
        base_url="https://openrouter.ai/api/v1",
        chat_completions_path="/chat/completions",
        api_key="secret",
        model_name="test-model",
        timeout=5,
        max_concurrency=1,
    )
    with LLMClient(
        settings,
        provider="openrouter",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.post_chat(
            "prompt", {"type": "object"}, task_name="resume.write"
        ) == {
            "ok": True
        }

    payload = json.loads(seen["payload"])
    assert payload["reasoning_effort"] == "medium"
    assert payload["temperature"] == policy_for("resume.write").temperature
    assert payload["provider"]["zdr"] is True


def test_client_disables_thinking_for_local_no_reasoning():
    settings = LLMSettings(
        base_url="http://localhost:5001",
        chat_completions_path="/v1/chat/completions",
        api_key="",
        model_name="test-model",
        timeout=5,
        max_concurrency=1,
    )
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    with LLMClient(
        settings,
        provider="llama-server",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.post_chat(
            "prompt", {"type": "object"}, task_name="jobs.role_identifier.classify"
        )

    assert seen["payload"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "provider" not in seen["payload"]
