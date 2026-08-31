import json

import httpx

from llm.client import LLMClient
from llm.policy import TaskPolicy
from llm.settings import LLMSettings


def test_client_sends_a_policy_to_openrouter():
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
    policy = TaskPolicy(
        name="custom.task",
        reasoning_effort="none",
        temperature=0.1,
        zero_data_retention=True,
    )

    with LLMClient(
        settings,
        provider="openrouter",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.post_chat("prompt", {"type": "object"}, policy=policy) == {
            "ok": True
        }

    payload = json.loads(seen["payload"])
    assert payload["reasoning_effort"] == "none"
    assert payload["temperature"] == 0.1
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
    policy = TaskPolicy(name="custom.task", reasoning_effort="none", temperature=0.2)
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
        client.post_chat("prompt", {"type": "object"}, policy=policy)

    assert seen["payload"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "provider" not in seen["payload"]
