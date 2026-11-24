"""Minimal OpenAI-compatible chat API adapter, standard library only."""
import json
import time
import urllib.error
import urllib.request


def chat_completion(prompt: str, *, model: str, base_url: str, api_key: str = "", max_tokens: int = 1024, temperature: float = 0.0):
    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "temperature": temperature}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(endpoint, json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as result:
        raw = json.loads(result.read().decode("utf-8"))
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    text = raw["choices"][0]["message"].get("content") or ""
    return {"response": text, "usage": raw.get("usage", {}), "latency_ms": latency_ms}
