import json
import os
import re
import time
from math import isfinite
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from ..model import chat_completion


CANDIDATES = ("candidate_a", "candidate_b")
ROLES = (*CANDIDATES, "judge_a")
EXTRA_FORBIDDEN = {"model", "messages", "max_tokens", "temperature", "stream", "api_key", "headers"}
# BigModel's account, quota, and entitlement errors need an external change before retrying.
GLM_TERMINAL_LIMITS = {"1113", "1308", "1309", "1310", "1311", *(str(code) for code in range(1313, 1322))}


def validate_models(models):
    for role in ROLES:
        model = models[role]
        for key in ("provider", "model", "base_url"):
            if not isinstance(model.get(key), str) or not model[key].strip():
                raise ValueError(f"Missing {role}.{key}")
        url = urlsplit(model["base_url"])
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path.rstrip("/").endswith("/chat/completions")):
            raise ValueError(f"Use a Chat Completions base URL without credentials for {role}")
        if url.scheme == "http" and url.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(f"Use HTTPS for remote provider {role}")
        env = model.get("api_key_env")
        if env is not None and (not isinstance(env, str) or not re.fullmatch("[A-Za-z_][A-Za-z0-9_]*", env)):
            raise ValueError(f"Invalid API key environment variable name for {role}")
        for key, low, high in (("timeout", 1, 600), ("retries", 0, 5),
                               ("max_tokens", 1, 32768), ("temperature", 0, 2)):
            value = model.get(key)
            expected = (int, float) if key in {"timeout", "temperature"} else int
            if isinstance(value, bool) or not isinstance(value, expected) or not low <= value <= high:
                raise ValueError(f"Invalid {role}.{key}")
        extra = model.get("extra", {})
        if not isinstance(extra, dict) or EXTRA_FORBIDDEN & extra.keys():
            raise ValueError(f"Invalid extra request parameters for {role}")
        assumed = model.get("estimated_output_tokens", model["max_tokens"])
        if type(assumed) is not int or not 1 <= assumed <= model["max_tokens"]:
            raise ValueError(f"Invalid estimated output for {role}")
        pricing = model.get("pricing")
        if pricing is not None:
            if not isinstance(pricing, dict):
                raise ValueError(f"Invalid pricing for {role}")
            rates = (pricing.get("input"), pricing.get("output"), pricing.get("cached_input", 0))
            if not pricing.get("currency") or any(type(rate) not in (float, int) or not isfinite(rate) or rate < 0
                                                  for rate in rates):
                raise ValueError(f"Invalid pricing for {role}")


def model_identity(model):
    return {key: model[key] for key in (
        "provider", "model", "base_url", "temperature", "max_tokens", "timeout", "retries"
    )} | {"extra": model.get("extra", {}), "revision": model.get("revision")}


def require_keys(models, roles):
    missing = sorted({models[role]["api_key_env"] for role in roles
                      if models[role].get("api_key_env") and not os.getenv(models[role]["api_key_env"], "").strip()})
    if missing:
        raise ValueError("Missing API environment variables: " + ", ".join(missing))


def glm_error_code(exc):
    if exc.fp is None:
        return None
    try:
        code = str(json.loads(exc.read(4096))["error"]["code"])
    except (ValueError, TypeError, KeyError, OSError):
        return None
    return code if re.fullmatch(r"[0-9]{3,5}", code) else None


def request(model, messages, parse=None, save=None):
    attempts = []
    for retry in range(model["retries"] + 1):
        started = time.perf_counter()
        delay = 2 ** retry
        retryable = True
        verdict = None
        try:
            result = chat_completion(
                "", messages=messages, model=model["model"], base_url=model["base_url"],
                api_key=os.environ.get(model.get("api_key_env") or "", ""), timeout=model["timeout"],
                temperature=model["temperature"], max_tokens=model["max_tokens"], extra=model.get("extra"),
            )
        except HTTPError as exc:
            status, result = "api_error", {"error": f"http_{exc.code}"}
            retryable = exc.code in {408, 429} or 500 <= exc.code < 600
            retry_after = (exc.headers or {}).get("Retry-After", "")
            if exc.code == 429 and model["provider"] == "glm":
                code = glm_error_code(exc)
                if code:
                    result["provider_error_code"] = code
                retryable = retryable and code not in GLM_TERMINAL_LIMITS
                delay = max(delay, 5 * (2 ** retry))
            if retry_after.isdigit():
                delay = max(delay, int(retry_after))
                retryable = retryable and delay <= 60
            exc.close()
        except (TimeoutError, URLError, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            status, result = "api_error", {
                "error": "timeout" if isinstance(reason, TimeoutError) else "network_error"
            }
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            status, result = "api_error", {"error": "invalid_api_response"}
        else:
            status = "ok"
            if not isinstance(result["response"], str):
                status, result = "api_error", {"error": "invalid_api_response", **result}
            elif parse is not None:
                try:
                    verdict = parse(result["response"], result.get("finish_reason"))
                except ValueError as exc:
                    status, result = "parse_error", {**result, "error": str(exc)}
        result.setdefault("latency_ms", round((time.perf_counter() - started) * 1000, 1))
        result["status"] = status
        attempts.append(result)
        if save is not None:
            save(verdict, attempts)
        if status == "ok" or not retryable or retry == model["retries"]:
            return verdict, attempts
        time.sleep(delay)
