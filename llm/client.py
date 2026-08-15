import json

import httpx

from llm.config import (
    API_KEY,
    BASE_URL,
    CHAT_COMPLETIONS_PATH,
    MAX_CONCURRENCY,
    MODEL_NAME,
    TEMPERATURE,
    TIMEOUT,
)


# Shared across the worker threads rather than one client each, so they reuse
# connections. httpx.Client is thread safe. The pool is capped at the same
# number of workers, since a fifth connection to a four slot server would only
# sit in the server's queue holding a socket open.
client = httpx.Client(
    base_url=BASE_URL,
    timeout=TIMEOUT,
    limits=httpx.Limits(max_connections=MAX_CONCURRENCY),
)


def post_chat(prompt: str, schema: dict, think: bool = True) -> dict:
    """
    Send a prompt to the model and return the parsed JSON content.

    Args:
        prompt (str): The full prompt to send.
        schema (dict): JSON schema constraining the reply.
        think (bool): Whether to let the model reason before answering. Off for
            the tasks that are a lookup rather than a judgement call.
    """
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object", "schema": schema},
        "temperature": TEMPERATURE,
    }
    if not think:
        # Two ways in, since either one alone covers only half the models.
        # reasoning_effort is llama-server's own switch and works whatever the
        # chat template says; enable_thinking is the template level one, read
        # by Qwen and friends and ignored by templates that lack it.
        payload["reasoning_effort"] = "none"
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    if MODEL_NAME:
        payload["model"] = MODEL_NAME

    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else None

    response = client.post(CHAT_COMPLETIONS_PATH, json=payload, headers=headers)

    try:
        return json.loads(response.json()["choices"][0]["message"]["content"])
    except Exception as e:
        raise ValueError(
            f"Failed to parse response: {e}. Response content: {response.text}"
        )
