from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Lock

from .api import CANDIDATES, model_identity, request
from .protocol import PROTOCOLS, judge_messages, parse_judgment
from .storage import Journal, fingerprint


class Evaluation:
    def __init__(self, tasks, models, protocol, output, workers, resume_from=()):
        self.models = models
        self.protocol = protocol
        self.jobs = [(task, role) for role in CANDIDATES for task in tasks]
        self.workers = workers
        self.new_requests = Counter()
        self.counter_lock = Lock()
        self.generations = Journal(output / "generations.jsonl")
        self.judgments = Journal(output / "judgments.jsonl")
        self.previous = {
            journal: [Journal(path / journal.path.name, read_only=True) for path in resume_from]
            for journal in (self.generations, self.judgments)
        }

    def cached(self, journal, key):
        row = journal.get(key)
        if row is not None:
            return row
        for source in self.previous[journal]:
            cached_row = source.get(key)
            if cached_row is None:
                continue
            if row is None or cached_row["status"] == "ok":
                row = cached_row
            if row["status"] == "ok":
                break
        if row is not None:
            journal.append(row)
        return row

    def count_request(self, role):
        with self.counter_lock:
            self.new_requests[role] += 1

    def generation(self, job, live=False):
        task, role = job
        model = self.models[role]
        identity = model_identity(model)
        messages = [{"role": "user", "content": task["prompt"]}]
        key = fingerprint([task["id"], task["dataset"], role, identity, messages])
        row = self.cached(self.generations, key)
        if not live or (row and row["status"] in {"ok", "empty_response"}):
            return row

        previous = row["attempts"] if row else []

        def save(_, attempts):
            self.count_request(role)
            final = attempts[-1]
            response = final.get("response") or ""
            status = "ok" if response.strip() else "empty_response"
            if final["status"] != "ok":
                status = "inference_error"
            self.generations.append({
                "key": key, "task_id": task["id"], "candidate": role, "candidate_model": identity,
                "status": status, "response": response, "response_sha256": fingerprint(response),
                "finish_reason": final.get("finish_reason"), "attempts": [*previous, *attempts],
                "retry_count": len(previous) + len(attempts) - 1,
            })

        request(model, messages, save=save)
        return self.generations.get(key)

    def judgment(self, task, role, generation, requirement, history, live):
        model = self.models["judge_a"]
        identity = model_identity(model)
        version = PROTOCOLS[self.protocol]
        messages = judge_messages(task, generation["response"], requirement, self.protocol, history)
        key = fingerprint([generation["key"], generation["response_sha256"], requirement["id"],
                           identity, version, messages])
        row = self.cached(self.judgments, key)
        if not live or (row and row["status"] == "ok"):
            return row, messages

        previous = row["attempts"] if row else []

        def save(verdict, attempts):
            self.count_request("judge_a")
            final = attempts[-1]
            status = "ok" if verdict else f"judge_{final['status']}"
            self.judgments.append({
                "key": key, "task_id": task["id"], "requirement_id": requirement["id"],
                "requirement": requirement["question"], "candidate": role,
                "candidate_model": generation["candidate_model"],
                "response_sha256": generation["response_sha256"], "judge_model": identity,
                "judge_prompt_version": version, "raw_judge_output": final.get("response"),
                "status": status, **(verdict or {"verdict": None, "reason": None, "evidence": None}),
                "usage": final.get("usage"), "latency_ms": final["latency_ms"],
                "attempts": [*previous, *attempts], "retry_count": len(previous) + len(attempts) - 1,
            })

        def parse(text, finish_reason):
            return parse_judgment(text, finish_reason, self.protocol, generation["response"])

        request(model, messages, parse, save)
        return self.judgments.get(key), messages

    def record(self, job, live=False):
        task, role = job
        generation = self.generation(job)
        history, checks = [], []
        blocked = not generation or generation["status"] != "ok"
        for requirement in task["requirements"]:
            row = None
            if not blocked:
                row, messages = self.judgment(task, role, generation, requirement, history, live)
                if self.protocol == "official":
                    if row and row["status"] == "ok":
                        history = [*messages, {"role": "assistant", "content": row["raw_judge_output"]}]
                    else:
                        blocked = True
            checks.append(row or {
                "requirement_id": requirement["id"], "requirement": requirement["question"],
                "status": "not_scored", "verdict": None,
            })
        return {
            "id": task["id"], "category": task["category"], "candidate": role,
            "instruction": task["instruction"], "input": task["input"],
            "generation": generation, "requirements": checks,
        }

    def run(self, mode):
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            if mode in {"generate", "end-to-end"}:
                for _ in pool.map(partial(self.generation, live=True), self.jobs):
                    pass
            if mode in {"judge", "end-to-end"}:
                return list(pool.map(partial(self.record, live=True), self.jobs))
        if mode == "aggregate":
            return [self.record(job) for job in self.jobs]
        return None
