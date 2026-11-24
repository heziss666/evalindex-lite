"""Compare saved runs without re-querying any LLM."""
import argparse
import json
from pathlib import Path


REAL_BENCHMARKS = {"MMLU-Pro", "MATH-500", "IFEval"}


def check_compatibility(entries):
    real_runs = any(REAL_BENCHMARKS.intersection(entry["benchmarks"]) for entry in entries)
    if real_runs:
        for entry in entries:
            benchmarks = REAL_BENCHMARKS.intersection(entry["benchmarks"])
            datasets = entry["datasets"] or {}
            scorers = entry["scorers"] or {}
            protocol = entry["protocol"] or {}
            if (entry["mode"] != "live" or not entry["data_sha256"] or entry["weights"] is None
                    or any(protocol.get(key) is None for key in ("inference", "temperature", "max_tokens"))
                    or not benchmarks
                    or not benchmarks.issubset(datasets) or not benchmarks.issubset(scorers)):
                raise ValueError("Real benchmark ranking requires live runs with dataset, scorer and protocol metadata")
            for name in benchmarks:
                keys = ("repository", "revision", "split", "prompt_version", "subset_seed", "shots")
                if any(datasets[name].get(key) is None for key in keys) or not scorers[name]:
                    raise ValueError(f"Incomplete comparison metadata for {name}")
    for field, label in {
        "data_sha256": "task data SHA-256",
        "weights": "benchmark weights",
        "datasets": "dataset revisions or prompt and sampling settings",
        "scorers": "scorer versions",
        "protocol": "evaluation protocol",
    }.items():
        settings = {json.dumps(entry[field], sort_keys=True) for entry in entries}
        if len(settings) > 1:
            raise ValueError(f"Incomparable runs: {label} differ")


def compare(paths):
    leaderboard = []
    for path in paths:
        summary = json.loads(Path(path).read_text(encoding="utf-8"))
        run = summary.get("run", {})
        leaderboard.append({
            "model": run.get("model", Path(path).parent.name),
            "run_path": str(path),
            "overall_index": summary.get("overall_index"),
            "benchmarks": {k: v.get("score") for k, v in summary.get("benchmarks", {}).items()},
            "scored": summary.get("scored"),
            "total": summary.get("total"),
            **{field: run.get(field) for field in (
                "data_sha256", "weights", "datasets", "scorers", "protocol", "mode", "model_revision"
            )},
        })
    check_compatibility(leaderboard)
    leaderboard.sort(key=lambda e: e["overall_index"] if e["overall_index"] is not None else float("-inf"), reverse=True)
    return {
        "data_sha256": leaderboard[0]["data_sha256"] if leaderboard else None,
        "leaderboard": leaderboard,
        "warning": "Compare only within this dataset subset, evaluation protocol and scoring configuration.",
    }


def main():
    parser = argparse.ArgumentParser(description="Combine EvalIndex Lite run summaries")
    parser.add_argument("summaries", nargs="+", help="Paths to summary.json files")
    parser.add_argument("--out", default="runs/leaderboard.json")
    args = parser.parse_args()
    output = compare(args.summaries)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
