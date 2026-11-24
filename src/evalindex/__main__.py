import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
from importlib.metadata import version
from pathlib import Path

from .analysis import badcase
from .scoring import score_task
from .model import chat_completion


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def dump_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def validate_ids(rows):
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate task or replay ids")


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def summarize(rows, weights):
    groups = {}
    for row in rows:
        b = row["benchmark"]
        if b not in groups:
            groups[b] = []
        groups[b].append(row)
    summary = {"benchmarks": {}, "overall_index": None, "scored": sum(x["score"] is not None for x in rows), "total": len(rows)}
    for name, items in sorted(groups.items()):
        scored = [x for x in items if x["score"] is not None]
        invalid = sum(not x["valid"] for x in items)
        result = {"score": (sum(x["score"] for x in scored) / len(scored) if scored else None),
                  "scored": len(scored), "total": len(items), "invalid": invalid}
        if items[0]["kind"] in {"mmlu_pro", "math_500"}:
            result.update(accuracy=result["score"], **badcase.counts(items))
        if any(x["kind"] == "constraints" for x in items):
            checks = [x["details"].get("checks", []) for x in scored if x["kind"] == "constraints"]
            count = sum(len(a) for a in checks)
            result["instruction_level"] = sum(sum(a) for a in checks) / count if count else None
        summary["benchmarks"][name] = result
    expected = set(weights)
    if expected and expected.issubset(summary["benchmarks"]) and all(summary["benchmarks"][n]["score"] is not None for n in expected):
        total_weight = sum(weights.values())
        summary["overall_index"] = 100 * sum(weights[n] * summary["benchmarks"][n]["score"] for n in weights) / total_weight
    return summary


def main():
    parser = argparse.ArgumentParser(prog="evalindex", description="EvalIndex Lite - evaluator scaffold")
    parser.add_argument("--data", default="data/demo_tasks.jsonl", help="JSONL tasks")
    parser.add_argument("--weights", default="configs/index_weights.json", help="Composite weights JSON")
    parser.add_argument("--replay", help="JSONL of saved responses (keyed by id)")
    parser.add_argument("--model", help="OpenAI-compatible model identifier")
    parser.add_argument("--model-revision", help="Model revision or weight fingerprint to record")
    parser.add_argument("--base-url", default=os.getenv("EVAL_BASE_URL", "http://localhost:8000/v1"))
    parser.add_argument("--api-key", default=os.getenv("EVAL_API_KEY", ""))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--output", default="runs/demo")
    args = parser.parse_args()

    tasks = load_jsonl(args.data)
    validate_ids(tasks)
    if not args.replay and not args.model:
        raise SystemExit("Supply --replay FILE or --model MODEL")
    if args.replay and args.model:
        raise SystemExit("Choose --replay or --model, not both")
    try:
        with open(args.weights, encoding="utf-8") as f:
            weights = json.load(f)
    except FileNotFoundError:
        weights = {}
    predictions = load_jsonl(args.replay) if args.replay else []
    validate_ids(predictions)
    replay = {x["id"]: x for x in predictions}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for t in tasks:
        prompt = t["prompt"]
        if args.replay:
            item = replay.get(t["id"])
            if item is None:
                raise SystemExit(f"Missing replay prediction for {t['id']}")
            model_result = {
                "response": item["response"], "usage": item.get("usage", {}),
                "latency_ms": item.get("latency_ms"), "finish_reason": item.get("finish_reason"),
                "served_model": item.get("served_model"),
            }
        else:
            model_result = chat_completion(prompt, model=args.model, base_url=args.base_url,
                                           api_key=args.api_key, temperature=args.temperature,
                                           max_tokens=args.max_tokens)
        graded = score_task(t, model_result["response"])
        result = {"id": t["id"], "benchmark": t["benchmark"], "kind": t["kind"],
                  **model_result, **graded}
        for key in ("gold", "source_id", "question", "category", "options", "level"):
            if key in t:
                result[key] = t[key]
        results.append(result)
    dump_jsonl(output / "results.jsonl", results)
    summary = summarize(results, weights)
    summary["run"] = {"model": args.model or "REPLAY_FIXTURE", "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                      "data": args.data, "data_sha256": hashlib.sha256(Path(args.data).read_bytes()).hexdigest(),
                      "temperature": args.temperature, "max_tokens": args.max_tokens,
                      "weights": weights, "note": "Demo score is not a public benchmark result"}
    dataset_metadata = {
        task["benchmark"]: {k: v for k, v in task["dataset"].items() if k != "source_index"}
        for task in tasks if "dataset" in task
    }
    if dataset_metadata:
        summary["run"].update(
            mode="replay" if args.replay else "live",
            model_revision=args.model_revision, commit=git_commit(), datasets=dataset_metadata,
            note="Zero-shot subset scores under the EvalIndex Lite protocol",
        )
        if "MATH-500" in dataset_metadata:
            summary["run"]["math_verify_version"] = version("math-verify")
        dump_jsonl(output / "badcases.jsonl", badcase.collect(
            row for row in results if row["kind"] in {"mmlu_pro", "math_500"}
        ))
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
