"""Minimal OpenAI-compatible chat API adapter, standard library only."""
import json
import time
import urllib.error
import urllib.request


def chat_completion(prompt: str, *, model: str, base_url: str, api_key: str = "",
                    max_tokens: int = 1024, temperature: float | None = 0.0,
                    messages=None, timeout=180, extra=None, token_limit_field="max_tokens"):
    endpoint = base_url.rstrip("/") + "/chat/completions"
    if token_limit_field not in {"max_tokens", "max_completion_tokens"}:
        raise ValueError("Unsupported token limit field")
    payload = {"model": model, "messages": messages if messages is not None else [{"role": "user", "content": prompt}],
               token_limit_field: max_tokens}
    if temperature is not None:
        payload["temperature"] = temperature
    if extra:
        core_fields = {"model", "messages", "max_tokens", "max_completion_tokens", "temperature"}
        if core_fields & extra.keys() or extra.get("stream"):
            raise ValueError("Extra parameters cannot override core options or enable streaming")
        payload.update(extra)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(endpoint, json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as result:
        raw = json.loads(result.read().decode("utf-8"))
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    choice = raw["choices"][0]
    return {
        "response": choice["message"].get("content") or "",
        "usage": raw.get("usage") or {},
        "latency_ms": latency_ms,
        "finish_reason": choice.get("finish_reason"),
        "served_model": raw.get("model"),
    }
