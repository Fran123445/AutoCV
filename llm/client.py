import json

import httpx

from llm.config import (
    API_KEY,
    BASE_URL,
    CHAT_COMPLETIONS_PATH,
    MODEL_NAME,
    TEMPERATURE,
    TIMEOUT,
)


client = httpx.Client(base_url=BASE_URL, timeout=TIMEOUT)


def post_chat(prompt: str, schema: dict) -> dict:
    """
    Send a prompt to the model and return the parsed JSON content.

    Args:
        prompt (str): The full prompt to send.
        schema (dict): JSON schema constraining the reply.
    """
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object", "schema": schema},
        "temperature": TEMPERATURE,
    }
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
