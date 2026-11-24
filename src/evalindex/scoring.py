"""Small demonstrator scorers. Not replacements for official benchmark scorers."""
import re
from decimal import Decimal, InvalidOperation

CHOICE_TAG = re.compile(r"(?im)^\s*(?:final\s*answer|answer|答案)\s*[:：]\s*([A-J])(?:\s|[.。!！]|$)")
NUMBER_TAG = re.compile(r"(?im)^\s*(?:final\s*answer|answer|答案|####)\s*[:：]?\s*([-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?(?:\s*/\s*[-+]?\d[\d,]*)?)\s*(?:[.。!！]|$)")


def extract_choice(response: str):
    hits = CHOICE_TAG.findall(response)
    if hits:
        return hits[-1].upper()
    clean = response.strip().upper().strip(".。!！")
    return clean if re.fullmatch("[A-J]", clean) else None


def parse_number(text: str):
    cleaned = str(text).replace(",", "").strip()
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?\s*/\s*[-+]?\d+", cleaned):
        a, b = cleaned.split("/")
        return Decimal(a.strip()) / Decimal(b.strip())
    return Decimal(cleaned)


def extract_number(response: str):
    hits = NUMBER_TAG.findall(response)
    if hits:
        return hits[-1]
    clean = response.strip()
    if re.fullmatch(r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?(?:\s*/\s*[-+]?\d[\d,]*)?", clean):
        return clean
    return None


def check_rule(response: str, rule: dict):
    kind = rule.get("type")
    value = rule.get("value", "")
    if kind == "contains":
        return str(value) in response
    if kind == "not_contains":
        return str(value) not in response
    if kind == "endswith":
        return response.rstrip().endswith(str(value))
    if kind == "startswith":
        return response.lstrip().startswith(str(value))
    if kind == "max_chars":
        return len(response) <= int(value)
    raise ValueError(f"Unknown demo rule: {kind}")


def score_task(task: dict, response: str):
    kind = task["kind"]
    if kind == "choice":
        pred = extract_choice(response)
        accepted = task.get("choices", list("ABCDEFGHIJ"))
        is_valid = pred in accepted
        return {"score": int(is_valid and pred == str(task["gold"]).upper()),
                "valid": is_valid, "predicted": pred, "details": {}}
    if kind == "number":
        pred = extract_number(response)
        if pred is None:
            return {"score": 0, "valid": False, "predicted": None, "details": {}}
        try:
            correct = parse_number(pred) == parse_number(task["gold"])
        except (InvalidOperation, ZeroDivisionError, ValueError):
            return {"score": 0, "valid": False, "predicted": pred, "details": {"error":"unparseable number"}}
        return {"score": int(correct), "valid": True, "predicted": pred, "details": {}}
    if kind == "constraints":
        checks = [bool(check_rule(response, r)) for r in task["rules"]]
        return {"score": int(all(checks)), "valid": True, "predicted": None,
                "details": {"checks": checks, "passed": sum(checks), "total": len(checks)}}
    if kind == "rubric":
        # Do not silently fake an LLM judge. Explicitly mark as unscored.
        return {"score": None, "valid": False, "predicted": None,
                "details": {"error":"rubric judge not connected; requires calibrated judge"}}
    raise ValueError(f"Unknown task kind: {kind}")
