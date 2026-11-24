from collections import Counter


def error_type(row):
    if row["kind"] == "ifeval" and row["score"] == 0:
        return "instruction_failure"
    if not row["valid"]:
        return "parse_failure"
    if row["score"] == 0:
        return "wrong_answer"
    return None


def counts(rows):
    types = Counter(error_type(row) for row in rows)
    reasons = Counter(
        row["details"]["parse_error"] for row in rows if error_type(row) == "parse_failure"
    )
    return {
        "correct": sum(row["score"] == 1 for row in rows),
        "wrong_answers": types["wrong_answer"],
        "parse_failures": types["parse_failure"],
        "parse_failure_reasons": dict(sorted(reasons.items())),
    }


def collect(rows):
    for row in rows:
        error = error_type(row)
        if error:
            yield {**row, "error_type": error}
