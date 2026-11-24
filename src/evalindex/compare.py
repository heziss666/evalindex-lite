"""Compare saved runs without re-querying any LLM."""
import argparse
import json
from pathlib import Path


def compare(paths):
    leaderboard = []
    for path in paths:
        summary = json.loads(Path(path).read_text(encoding="utf-8"))
        leaderboard.append({
            "model": summary.get("run", {}).get("model", Path(path).parent.name),
            "run_path": str(path),
            "overall_index": summary.get("overall_index"),
            "benchmarks": {k: v.get("score") for k, v in summary.get("benchmarks", {}).items()},
            "scored": summary.get("scored"),
            "total": summary.get("total"),
            "data_sha256": summary.get("run", {}).get("data_sha256"),
            "weights": summary.get("run", {}).get("weights"),
        })
    hashes = {entry["data_sha256"] for entry in leaderboard}
    if len(hashes) > 1:
        raise ValueError("Incomparable runs: task data SHA-256 differs")
    weight_settings = {json.dumps(entry["weights"], sort_keys=True) for entry in leaderboard}
    if len(weight_settings) > 1:
        raise ValueError("Incomparable runs: benchmark weights differ")
    leaderboard.sort(key=lambda e: e["overall_index"] if e["overall_index"] is not None else float("-inf"), reverse=True)
    return {"data_sha256": next(iter(hashes), None), "leaderboard": leaderboard,
            "warning": "Composite scores compare runs on same task file and weights only; sample fixtures are not real benchmark scores."}


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
