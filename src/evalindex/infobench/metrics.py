from collections import Counter
from statistics import mean

from .api import CANDIDATES, ROLES
from .protocol import judge_messages
from .storage import write_report


def proportion(numerator, denominator):
    return numerator / denominator if denominator else None


def scores(rows):
    checks = [check for row in rows for check in row["requirements"]]
    total = len(checks)
    judged = [check for check in checks if check["status"] == "ok"]
    errors = sum(check["status"].startswith("judge_") for check in checks)
    passed = sum(check["verdict"] == "pass" for check in judged)
    complete = len(judged) == total and total > 0
    passes_per_task = [
        sum(check["verdict"] == "pass" for check in row["requirements"]) / len(row["requirements"])
        for row in rows
    ]
    return {
        "drfr": proportion(passed, total) if complete else None,
        "observed_requirement_pass_rate": proportion(passed, len(judged)),
        "prompt_level_mean_pass": mean(passes_per_task) if complete else None,
        "prompt_level_all_pass": mean(rate == 1 for rate in passes_per_task) if complete else None,
        "scoring_coverage": proportion(len(judged), total),
        "judge_error_rate": proportion(errors, errors + len(judged)),
        "judge_errors": errors, "judge_attempted_requirements": errors + len(judged),
        "prompts": len(rows), "requirements": total, "passed": passed, "scored": len(judged),
        "complete": complete,
    }


def usage_tokens(usage):
    prompt = usage.get("prompt_tokens_details") or {}
    completion = usage.get("completion_tokens_details") or {}
    return {
        "input": usage.get("prompt_tokens"),
        "output": usage.get("completion_tokens"),
        "reasoning": completion.get("reasoning_tokens", usage.get("reasoning_tokens")),
        "cached": prompt.get("cached_tokens", usage.get("prompt_cache_hit_tokens")),
        "uncached": usage.get("prompt_cache_miss_tokens"),
    }


def cost(tokens, pricing):
    if not pricing or tokens["input"] is None or tokens["output"] is None:
        return None
    cached = tokens.get("cached")
    if cached is None and tokens.get("uncached") is not None:
        cached = tokens["input"] - tokens["uncached"]
    cached = max(0, min(tokens["input"], cached or 0))
    return (((tokens["input"] - cached) * pricing["input"] + tokens["output"] * pricing["output"]
             + cached * pricing.get("cached_input", pricing["input"])) / 1_000_000)


def usage_report(attempts, pricing):
    samples = [usage_tokens(attempt.get("usage") or {}) for attempt in attempts]
    costs = [cost(tokens, pricing) for tokens in samples]
    known_costs = [value for value in costs if value is not None]
    observed = {field: [item[field] for item in samples if item[field] is not None]
                for field in ("input", "output", "reasoning", "cached", "uncached")}
    return {
        "requests": len(attempts),
        "tokens_reported": {field: sum(values) if values else None for field, values in observed.items()},
        "requests_reporting_token_field": {field: len(values) for field, values in observed.items()},
        "mean_request_latency_ms": mean(a["latency_ms"] for a in attempts) if attempts else None,
        "estimated_reported_cost": sum(known_costs) if known_costs else None,
        "requests_without_cost": len(costs) - len(known_costs),
        "currency": pricing["currency"] if pricing else None,
    }


def dry_run(tasks, models, protocol):
    counts = {role: Counter() for role in ROLES}
    assumed = {role: models[role].get("estimated_output_tokens", models[role]["max_tokens"])
               for role in ROLES}
    for task in tasks:
        for role in CANDIDATES:
            candidate = counts[role]
            candidate["requests"] += 1
            candidate["input"] += (len(task["prompt"]) + 3) // 4 + 8
            candidate["output"] += assumed[role]
            response, history = "x" * (assumed[role] * 4), []
            for requirement in task["requirements"]:
                judge = counts["judge_a"]
                messages = judge_messages(task, response, requirement, protocol, history)
                judge["requests"] += 1
                judge["input"] += sum((len(msg["content"]) + 3) // 4 + 8 for msg in messages)
                judge["output"] += assumed["judge_a"]
                if protocol == "official":
                    history = [*messages, {"role": "assistant", "content": "x" * (assumed["judge_a"] * 4)}]
    role_estimates = {}
    totals = Counter()
    for role, count in counts.items():
        pricing = models[role].get("pricing")
        amount = cost(count, pricing)
        role_estimates[role] = {
            **count, "estimated_cost": amount,
            "currency": pricing["currency"] if pricing else None,
        }
        if amount is not None:
            totals[pricing["currency"]] += amount
    return {
        "tasks": len(tasks), "requirements_per_candidate": sum(len(t["requirements"]) for t in tasks),
        "requests_without_retries": sum(count["requests"] for count in counts.values()),
        "task_types": dict(Counter(task["task_type"] for task in tasks)),
        "categories": dict(Counter(task["category"] for task in tasks)),
        "assumed_output_tokens_per_request": assumed, "roles": role_estimates,
        "estimated_cost_by_currency": dict(totals),
        "estimate": "Approximate input at 4 characters/token plus message overhead. No cache discounts or retries.",
    }


def review_sample(rows, limit=20):
    votes = {}
    for row in rows:
        for check in row["requirements"]:
            if check["status"] == "ok":
                votes.setdefault(check["requirement_id"], set()).add(check["verdict"])
    buckets = {}
    for row in rows:
        generation = row["generation"] or {}
        for check in row["requirements"]:
            if check["status"] == "not_scored":
                continue
            disagreement = len(votes.get(check["requirement_id"], ())) > 1
            key = (row["candidate"], check["status"], check["verdict"],
                   generation.get("finish_reason") == "length", disagreement)
            buckets.setdefault(key, []).append({
                "task_id": row["id"], "category": row["category"], "candidate": row["candidate"],
                "instruction": row["instruction"], "input": row["input"],
                "response": generation.get("response"), "candidate_finish_reason": generation.get("finish_reason"),
                "different_candidate_verdicts": disagreement,
                **{field: check.get(field) for field in (
                    "requirement_id", "requirement", "verdict", "reason", "evidence", "status", "raw_judge_output"
                )},
                "human_verdict": None, "human_notes": None,
            })
    result = []
    for index in range(max(map(len, buckets.values()), default=0)):
        for bucket in buckets.values():
            if index < len(bucket):
                result.append(bucket[index])
                if len(result) == limit:
                    return result
    return result


def publish(output, rows, models, metadata):
    totals, result_rows, badcases = {}, [], []
    attempts = {role: [] for role in ROLES}
    for role in CANDIDATES:
        selected = [row for row in rows if row["candidate"] == role]
        categories = sorted({row["category"] for row in selected})
        totals[role] = {
            "model": models[role]["model"], **scores(selected),
            "categories": {c: scores([row for row in selected if row["category"] == c]) for c in categories},
        }
    for row in rows:
        gen = row["generation"] or {}
        attempts[row["candidate"]].extend(gen.get("attempts", []))
        status = gen.get("status", "generation_missing")
        common = {"id": row["id"], "candidate": row["candidate"], "category": row["category"]}
        result_rows.append({
            **common, **scores([row]), "generation_status": status, "finish_reason": gen.get("finish_reason"),
            "response_sha256": gen.get("response_sha256"),
            "unscored_requirement_ids": [
                check["requirement_id"] for check in row["requirements"] if check["status"] != "ok"
            ],
        })
        if status != "ok" or gen.get("finish_reason") == "length":
            badcases.append({**common, "error_type": status if status != "ok" else "response_truncated"})
        for check in row["requirements"]:
            attempts["judge_a"].extend(check.get("attempts", []))
            if check["verdict"] == "fail" or check["status"].startswith("judge_"):
                badcases.append({
                    **common, "error_type": "requirement_failure" if check["verdict"] == "fail" else check["status"],
                    "requirement_id": check["requirement_id"], "requirement": check["requirement"],
                    "response_sha256": gen.get("response_sha256"), "judgment_key": check["key"],
                })
    ranking = [
        {"candidate": role, "model": row["model"], "drfr": row["drfr"], "scoring_coverage": row["scoring_coverage"]}
        for role, row in totals.items() if row["complete"]
    ]
    ranking.sort(key=lambda row: row["drfr"], reverse=True)
    summary = {
        **metadata, "candidates": totals,
        "api": {role: usage_report(items, models[role].get("pricing")) for role, items in attempts.items()},
    }
    write_report(output / "results.jsonl", result_rows, jsonl=True)
    write_report(output / "badcases.jsonl", badcases, jsonl=True)
    write_report(output / "summary.json", summary)
    write_report(output / "leaderboard.json", {**metadata, "leaderboard": ranking})
    write_report(output / "human_review.jsonl", review_sample(rows), jsonl=True)
    return summary
