import argparse
import hashlib
import json
import os
from pathlib import Path

from ..__main__ import git_commit, load_jsonl, validate_ids
from ..datasets.infobench import load_rows, sample_tasks
from .api import CANDIDATES, ROLES, model_identity, require_keys, validate_models
from .metrics import dry_run, publish
from .pipeline import Evaluation
from .protocol import PROTOCOLS
from .storage import run_lock, write_report


DATA_DIR = Path("data/benchmarks/m2")
CONFIG = Path("configs/infobench.json")
MODES = ("dry-run", "generate", "judge", "aggregate", "end-to-end")


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_env(path, models):
    if not path.exists():
        return
    allowed = {model.get("api_key_env") for model in models.values()}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() in allowed:
            value = value.strip().strip("'\"")
            if value:
                os.environ.setdefault(name.strip(), value)


def export_tasks(args, settings):
    count = args.count if args.count is not None else settings["sample_count"]
    smoke_count = settings["smoke_count"]
    if type(smoke_count) is not int or not 1 <= smoke_count <= count:
        raise ValueError("Require 1 <= smoke_count <= sample count")
    tasks = sample_tasks(load_rows(args.source), count, settings["seed"])
    output = args.output or DATA_DIR
    output.mkdir(parents=True, exist_ok=True)
    split_files = {}
    for name, rows in (("tasks", tasks), ("smoke", tasks[:smoke_count])):
        path = output / f"{name}.jsonl"
        write_report(path, rows, jsonl=True)
        plan = dry_run(rows, settings["models"], "official")
        split_files[name] = {"sha256": file_sha256(path), **{
            key: plan[key] for key in ("tasks", "requirements_per_candidate", "task_types", "categories")
        }}
    report = {"dataset": tasks[0]["dataset"], "files": split_files}
    write_report(output / "manifest.json", report)
    return report


def evaluate(args, settings):
    tasks = load_jsonl(args.data)
    validate_ids(tasks)
    if not tasks or any(t["kind"] != "infobench" or t["dataset"] != tasks[0]["dataset"] for t in tasks):
        raise ValueError("Expected a nonempty InFoBench task file with consistent dataset metadata")
    for task in tasks:
        if not task["requirements"]:
            raise ValueError(f"Missing requirements for {task['id']}")
        validate_ids(task["requirements"])
    models = settings["models"]
    metadata = {
        "benchmark": "InFoBench", "data_sha256": file_sha256(args.data), "dataset": tasks[0]["dataset"],
        "judge_prompt_version": PROTOCOLS[args.protocol], "commit": git_commit(),
        "models": {role: model_identity(models[role]) for role in ROLES},
        "pricing": {role: models[role].get("pricing") for role in ROLES},
    }
    if args.mode == "dry-run":
        return {**metadata, **dry_run(tasks, models, args.protocol)}
    if args.mode != "aggregate" and len(tasks) > settings["smoke_count"] and not args.confirm_formal:
        raise ValueError("Paid run exceeds the smoke size. Add --confirm-formal after approving the estimate.")
    roles = {"generate": CANDIDATES, "judge": ("judge_a",), "aggregate": (), "end-to-end": ROLES}
    if roles[args.mode]:
        load_env(args.env_file, models)
        require_keys(models, roles[args.mode])
    workers = args.workers if args.workers is not None else settings["workers"]
    if type(workers) is not int or not 1 <= workers <= 32:
        raise ValueError("Expected between 1 and 32 workers")
    stage = "smoke" if len(tasks) <= settings["smoke_count"] else "tasks"
    output = args.output or Path("runs/m2") / stage / args.protocol
    output.mkdir(parents=True, exist_ok=True)
    if args.resume_from:
        if not args.resume_from.is_dir() or args.resume_from.resolve() == output.resolve():
            raise ValueError("--resume-from must be a different existing run directory")
    with run_lock(output):
        evaluation = Evaluation(tasks, models, args.protocol, output, workers, args.resume_from)
        rows = evaluation.run(args.mode)
        new_requests = {role: evaluation.new_requests[role] for role in ROLES}
        if rows is None:
            generations = [evaluation.generation(job) for job in evaluation.jobs]
            return {"output": str(output), "expected": len(generations),
                    "requests_this_command": new_requests,
                    "generated": sum(row is not None and row["status"] == "ok" for row in generations)}
        return {**publish(output, rows, models, metadata), "requests_this_command": new_requests}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export and evaluate InFoBench")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("--source", type=Path, help="Optional local copy of the pinned official JSONL")
    export.add_argument("--count", type=int)
    export.add_argument("--config", type=Path, default=CONFIG)
    export.add_argument("--output", type=Path)
    for mode in MODES:
        sub = subparsers.add_parser(mode)
        sub.add_argument("--config", type=Path, default=CONFIG)
        sub.add_argument("--data", type=Path, default=DATA_DIR / "smoke.jsonl")
        sub.add_argument("--output", type=Path)
        sub.add_argument("--protocol", choices=PROTOCOLS, default="official")
        sub.add_argument("--workers", type=int)
        sub.add_argument("--env-file", type=Path, default=Path(".env"))
        sub.add_argument("--resume-from", type=Path)
        sub.add_argument("--confirm-formal", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = json.loads(args.config.read_text(encoding="utf-8"))
        validate_models(settings["models"])
        report = export_tasks(args, settings) if args.mode == "export" else evaluate(args, settings)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"InFoBench: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
