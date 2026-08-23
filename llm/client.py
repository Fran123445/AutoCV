import json
import threading
import time

import httpx

from run_log import LLMCall, prompt_fingerprint, record_call, utc_now

from config import (
    API_KEY,
    BASE_URL,
    CHAT_COMPLETIONS_PATH,
    MAX_CONCURRENCY,
    MODEL_NAME,
    REASONING_EFFORT_BY_TASK,
    TEMPERATURE,
    TIMEOUT,
)


_client: httpx.Client | None = None
_client_lock = threading.Lock()


def get_client() -> httpx.Client:
    """
    The shared HTTP client, built on first use.

    One client across the worker threads rather than one each, so they reuse
    connections; httpx.Client is thread safe. The pool is capped at the same
    number of workers, since a further connection would only queue at the
    server anyway. Built lazily so importing a task does not open a pool
    before a caller has had the chance to set the environment or swap it.
    """
    global _client

    if _client is None:
        with _client_lock:
            # Re-checked under the lock: two workers can pass the test above
            # before either takes it, and the loser would otherwise replace a
            # client the winner is already holding connections on.
            if _client is None:
                _client = httpx.Client(
                    base_url=BASE_URL,
                    timeout=TIMEOUT,
                    limits=httpx.Limits(max_connections=MAX_CONCURRENCY),
                )

    return _client


def post_chat(
    prompt: str,
    schema: dict,
    task_name: str = "unknown",
    reasoning_effort: str | None = None,
) -> dict:
    """
    Send a prompt to the model and return the parsed JSON content.

    Also records the call against the posting being processed, when there is
    one. Recording happens here rather than in the tasks because this is the
    only place that sees the timings, the usage figures and the model the
    server picked.

    Args:
        prompt (str): The full prompt to send.
        schema (dict): JSON schema constraining the reply.
        task_name (str): Who is asking, as 'pipeline.package.pass'. The
            pipeline prefix disambiguates identical pass names across
            pipelines, e.g. tech_identifier for a posting vs. a repo. Also the
            key the per-task reasoning effort is looked up under.
        reasoning_effort (str | None): How hard the model reasons ("low",
            "medium", "high", or "none" to turn it off). An explicit value wins;
            None reads the effort keyed under task_name, which every task is
            listed under in REASONING_EFFORT_BY_TASK.

    Raises:
        KeyError: task_name has no entry in REASONING_EFFORT_BY_TASK and no
            reasoning_effort was passed. Every pass decides its effort there, so
            a miss is a task added without one.
    """
    effort = reasoning_effort or REASONING_EFFORT_BY_TASK[task_name]

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object", "schema": schema},
        "temperature": TEMPERATURE,
        "reasoning_effort": effort,
    }
    if effort == "none":
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    if MODEL_NAME:
        payload["model"] = MODEL_NAME

    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else None

    call = LLMCall(
        task_name=task_name,
        started_at=utc_now(),
        temperature=TEMPERATURE,
        reasoning_effort=effort,
        prompt_sha1=prompt_fingerprint(prompt),
    )
    # perf_counter and not the two timestamps: they are rounded to the second,
    # and a lookup call comes back well inside one.
    started = time.perf_counter()
    response = None

    try:
        response = get_client().post(CHAT_COMPLETIONS_PATH, json=payload, headers=headers)
        call.http_status = response.status_code

        body = response.json()
        # An error reply carries no usage and no choices, so read what is there
        # before the line that will raise.
        usage = body.get("usage") or {}
        call.prompt_tokens = usage.get("prompt_tokens")
        call.completion_tokens = usage.get("completion_tokens")
        call.model_name = body.get("model")

        content = json.loads(body["choices"][0]["message"]["content"])
    except Exception as e:
        call.status = "failed"
        call.error = repr(e)
        raise ValueError(
            # response is None when the request never came back at all, which
            # is what a timeout looks like from here.
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
