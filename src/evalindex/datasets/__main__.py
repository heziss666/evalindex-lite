import argparse
import json
import random
from pathlib import Path

from ..__main__ import dump_jsonl, validate_ids
from . import ifeval, math_500, mmlu_pro


BUILDERS = {
    "MMLU-Pro": mmlu_pro.make_task,
    "MATH-500": math_500.make_task,
    "IFEval": ifeval.make_task,
}


def load_rows(name, dataset):
    if name == "IFEval":
        return ifeval.load_rows(dataset)

    from datasets import load_dataset

    return load_dataset(dataset["repository"], revision=dataset["revision"], split=dataset["split"])


def main():
    parser = argparse.ArgumentParser(description="Export pinned benchmark subsets to JSONL")
    parser.add_argument("--config", default="configs/benchmarks.json", type=Path)
    parser.add_argument("--output", default="data/benchmarks", type=Path)
    parser.add_argument("--count", default=30, type=int, help="Number of questions per dataset")
    parser.add_argument("--smoke-count", default=5, type=int, help="Prefix size per dataset")
    parser.add_argument("--benchmarks", nargs="+", choices=BUILDERS, default=["MMLU-Pro", "MATH-500"])
    args = parser.parse_args()
    if not 0 < args.smoke_count <= args.count:
        parser.error("Require 0 < smoke-count <= count")

    config = json.loads(args.config.read_text(encoding="utf-8"))
    tasks, smoke = [], []
    for name in args.benchmarks:
        builder = BUILDERS[name]
        dataset = config["datasets"][name]
        rows = load_rows(name, dataset)
        if args.count > len(rows):
            parser.error(f"{name} has {len(rows)} questions, fewer than --count {args.count}")
        indices = random.Random(config["subset_seed"]).sample(range(len(rows)), args.count)
        subset = []
        for index in indices:
            task = builder(rows[index])
            task["dataset"] = {
                **dataset, "subset_seed": config["subset_seed"], "source_index": index,
                "shots": config["shots"],
            }
            subset.append(task)
        tasks.extend(subset)
        smoke.extend(subset[:args.smoke_count])
        print(f"{name}: {len(subset)} of {len(rows)} examples")

    validate_ids(tasks)
    args.output.mkdir(parents=True, exist_ok=True)
    dump_jsonl(args.output / "tasks.jsonl", tasks)
    dump_jsonl(args.output / "smoke.jsonl", smoke)


if __name__ == "__main__":
    main()
