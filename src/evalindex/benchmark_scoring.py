import re
import sys
from functools import lru_cache


CHOICE = re.compile(r"Final Answer:[ \t]*([A-Z])", re.I | re.ASCII)
MATH_LINE = re.compile(r"Final Answer:[ \t]*(.+)", re.I | re.ASCII)
TIMEOUT = None if sys.platform == "win32" else 5


def result(predicted, correct=False, error=None, **details):
    return {
        "score": int(correct), "valid": error is None, "predicted": predicted,
        "details": {"parse_error": error, **details} if error else details,
    }


def score_mmlu_pro(task, response):
    match = CHOICE.fullmatch(response.strip())
    if not match:
        return result(None, error="choice_format" if response.strip() else "empty_response")
    predicted = match[1].upper()
    if predicted not in task["choices"]:
        return result(predicted, error="option_out_of_range")
    return result(predicted, correct=predicted == task["gold"])


@lru_cache(maxsize=512)
def parse_math(answer):
    from math_verify import LatexExtractionConfig, parse

    return parse(
        f"${answer}$", extraction_config=(LatexExtractionConfig(),),
        fallback_mode="no_fallback", extraction_mode="first_match", parsing_timeout=TIMEOUT,
    )


def score_math_500(task, response):
    from math_verify import verify

    lines = response.strip().splitlines()
    if not lines:
        return result(None, error="empty_response")
    match = MATH_LINE.fullmatch(lines[-1].strip())
    if not match:
        return result(None, error="missing_final_answer")
    candidate = match[1].strip()
    if candidate.startswith("$$") and candidate.endswith("$$"):
        candidate = candidate[2:-2].strip()
    elif candidate.startswith("$") and candidate.endswith("$"):
        candidate = candidate[1:-1].strip()
    if not candidate or "$" in candidate:
        return result(candidate, error="unparseable_math")

    reference = parse_math(task["gold"])
    if not reference:
        raise ValueError(f"Math-Verify could not parse the gold for {task['id']}")
    parsed = parse_math(candidate)
    if not parsed:
        return result(candidate, error="unparseable_math")
    return result(
        candidate, correct=verify(reference, parsed, timeout_seconds=TIMEOUT),
        normalized_prediction=[str(value) for value in parsed],
    )
