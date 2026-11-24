import hashlib
import json
import tempfile
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

from evalindex.datasets import infobench as dataset
from evalindex.infobench import api
from evalindex.infobench.__main__ import main
from evalindex.infobench.metrics import review_sample, scores, usage_report
from evalindex.infobench.protocol import judge_messages, parse_judgment
from evalindex.infobench.storage import Journal, run_lock, write_report


def source_row(index, task_type="user", count=2):
    return {
        "id": f"{task_type}_oriented_task_{index}", "category": f"category-{index}",
        "subset": "Easy_set" if task_type == "user" else "Hard_set",
        "instruction": "Write a response.", "input": "Sample input.",
        "decomposed_questions": [f"Private check {i}?" for i in range(count)],
        "question_label": [["Content"] for _ in range(count)],
    }


class TestInFoBench(TestCase):
    def test_pinned_bytes_and_validation(self):
        payload = json.dumps(source_row(1)).encode()
        with patch.object(dataset, "SOURCE_SHA256", hashlib.sha256(payload).hexdigest()):
            self.assertEqual(dataset.read_source(payload), [source_row(1)])
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                dataset.read_source(payload + b" ")
        invalid = {**source_row(1), "question_label": []}
        with self.assertRaisesRegex(ValueError, "requirements"):
            dataset.make_task(invalid, 42)

    def test_sampling_prefix_and_unique_ids(self):
        rows = [source_row(i, kind) for kind in ("user", "domain") for i in range(5)]
        full = dataset.sample_tasks(rows, 10, 42)
        self.assertEqual(full[:5], dataset.sample_tasks(rows, 5, 42))
        self.assertEqual({task["task_type"] for task in full[:2]}, {"user", "domain"})
        self.assertEqual(len({r["id"] for t in full for r in t["requirements"]}), 20)
        self.assertNotIn("Private check", full[0]["prompt"])
        self.assertNotIn("Content", full[0]["prompt"])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            dataset.sample_tasks([rows[0], rows[0]], 1, 42)

    def test_protocols_and_parsers(self):
        task = dataset.make_task(source_row(1), 42)
        r1, r2 = task["requirements"]
        first = judge_messages(task, "Example answer.", r1, "official", [])
        self.assertTrue(first[0]["content"].endswith('Input:\n"Sample input."\n\nGenerated Text:\n'
                                                     '"Example answer."\n\nQuestion:\nPrivate check 0?\n'))
        history = [*first, {"role": "assistant", "content": "Yes"}]
        self.assertEqual(judge_messages(task, "Example answer.", r2, "official", history)[:-1], history)
        self.assertEqual(parse_judgment("No, although YES appears", "stop", "official", "")["verdict"], "fail")
        self.assertEqual(parse_judgment("The answer is YES", "stop", "official", "")["verdict"], "pass")
        atomic = judge_messages(task, "Example answer.", r2, "atomic", history)
        self.assertEqual(len(atomic), 2)
        self.assertNotIn("Private check 0", atomic[1]["content"])
        valid = '{"verdict":"pass","reason":"Relevant","evidence":"Example"}'
        self.assertEqual(parse_judgment(valid, "stop", "atomic", "Example answer.")["evidence"], "Example")
        for text, finish, protocol in (
            ("", "stop", "official"), ("YES", "length", "official"), ("Maybe", "stop", "official"),
            ('{"verdict":"maybe"}', "stop", "atomic"), ('{"verdict":"pass"}', "stop", "atomic"),
            (valid.replace("Example", "invented"), "stop", "atomic"),
        ):
            with self.subTest(text=text, finish=finish), self.assertRaises(ValueError):
                parse_judgment(text, finish, protocol, "Example answer.")

    def test_mixed_requirement_counts_and_missing_scores(self):
        passed = {"status": "ok", "verdict": "pass"}
        failed = {"status": "ok", "verdict": "fail"}
        error = {"status": "judge_parse_error", "verdict": None}
        rows = [{"requirements": [passed]}, {"requirements": [passed, failed, failed]}]
        result = scores(rows)
        self.assertEqual(result["drfr"], 0.5)
        self.assertAlmostEqual(result["prompt_level_mean_pass"], 2 / 3)
        self.assertEqual(result["prompt_level_all_pass"], 0.5)
        rows[1]["requirements"][2] = error
        result = scores(rows)
        self.assertIsNone(result["drfr"])
        self.assertEqual(result["scoring_coverage"], 0.75)
        self.assertEqual(result["judge_error_rate"], 0.25)

    def test_rate_limits_timeout_and_permanent_errors(self):
        settings = json.loads(Path("configs/infobench.json").read_text(encoding="utf-8"))["models"]["judge_a"]
        response = {"response": "Yes", "finish_reason": "stop", "usage": {}, "latency_ms": 10}
        limited = HTTPError("https://example.invalid", 429, "", {"Retry-After": "3"}, None)
        with patch.object(api, "chat_completion", side_effect=[TimeoutError(), limited, response]), (
                patch.object(api.time, "sleep")) as sleep:
            _, attempts = api.request(settings, [])
        self.assertEqual([a.get("error") for a in attempts], ["timeout", "http_429", None])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 3])
        denied = HTTPError("https://example.invalid", 401, "", {}, None)
        with patch.object(api, "chat_completion", side_effect=denied) as call:
            _, attempts = api.request(settings, [])
        self.assertEqual(call.call_count, 1)
        self.assertEqual(attempts[0]["error"], "http_401")

    def test_reported_usage_and_absence(self):
        attempts = [
            {"latency_ms": 10, "usage": {"prompt_tokens": 100, "completion_tokens": 4,
                                         "prompt_cache_hit_tokens": 20}},
            {"latency_ms": 20},
        ]
        report = usage_report(attempts, {"input": 10, "output": 25, "cached_input": 1, "currency": "CNY"})
        self.assertIsNone(report["tokens_reported"]["reasoning"])
        self.assertEqual(report["requests_without_cost"], 1)
        self.assertAlmostEqual(report["estimated_reported_cost"], 0.00092)

    def test_glm_quota_stops_retries_and_records_only_error_code(self):
        model = json.loads(Path("configs/infobench.json").read_text(encoding="utf-8"))["candidate_b_alternatives"]["glm"]
        body = BytesIO(b'{"error":{"code":"1308","message":"private details"}}')
        denied = HTTPError("https://example.invalid", 429, "", {}, body)
        with patch.object(api, "chat_completion", side_effect=denied) as call, patch.object(api.time, "sleep") as sleep:
            _, attempts = api.request(model, [])
        self.assertEqual(call.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(attempts[0]["provider_error_code"], "1308")
        self.assertNotIn("private details", json.dumps(attempts))

    def test_human_review_samples_each_candidates_passes_and_failures(self):
        rows = [
            {
                "id": f"task-{index}", "category": "fixture", "candidate": role,
                "instruction": "Write a response.", "input": "",
                "generation": {"response": "Candidate answer.", "finish_reason": "stop"},
                "requirements": [
                    {"requirement_id": f"task-{index}:r1", "verdict": "pass", "status": "ok"},
                    {"requirement_id": f"task-{index}:r2", "verdict": "fail", "status": "ok"},
                ],
            }
            for role in ("candidate_a", "candidate_b") for index in range(12)
        ]
        sample = review_sample(rows)
        self.assertEqual(len(sample), 20)
        self.assertEqual({(item["candidate"], item["verdict"]) for item in sample}, {
            ("candidate_a", "pass"), ("candidate_a", "fail"),
            ("candidate_b", "pass"), ("candidate_b", "fail"),
        })
        self.assertTrue(all(item["human_verdict"] is None for item in sample))

    def test_judge_parse_failure_is_retried_and_saved(self):
        model = json.loads(Path("configs/infobench.json").read_text(encoding="utf-8"))["models"]["judge_a"]
        first = {"response": "Yes", "finish_reason": "length", "latency_ms": 1}
        second = {"response": "No", "finish_reason": "stop", "latency_ms": 2}
        recorded = []

        def save(verdict, attempts):
            recorded.append((verdict, attempts[-1]["status"]))

        with patch.object(api, "chat_completion", side_effect=[first, second]), patch.object(api.time, "sleep"):
            verdict, attempts = api.request(
                model, [], lambda text, finish: parse_judgment(text, finish, "official", ""), save
            )
        self.assertEqual(recorded, [(None, "parse_error"), (verdict, "ok")])
        self.assertEqual(attempts[0]["error"], "truncated_judge_output")
        self.assertEqual(verdict["verdict"], "fail")

    def test_partial_checkpoint_tail_and_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            with run_lock(parent), self.assertRaisesRegex(ValueError, "Another command"):
                with run_lock(parent):
                    pass
            path = parent / "records.jsonl"
            path.write_bytes(b'{"key":"first"}\n{"interrupted"')
            journal = Journal(path)
            journal.append({"key": "second"})
            self.assertEqual(list(Journal(path).rows), ["first", "second"])


class MockAPI(BaseHTTPRequestHandler):
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append(payload)
        role = payload["model"]
        if role != "test-judge":
            content = "Candidate answer."
        elif payload["messages"][0]["role"] == "system":
            content = '{"verdict":"pass","reason":"Present","evidence":"answer"}'
        else:
            content = "Yes"
        body = json.dumps({
            "model": role, "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 25, "completion_tokens": 3},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class TestModes(TestCase):
    def test_modes_resume_and_protocol_separation(self):
        with tempfile.TemporaryDirectory() as tmp, ThreadingHTTPServer(("127.0.0.1", 0), MockAPI) as server:
            server.calls = []
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(thread.join, 5)
            try:
                self.exercise_modes(Path(tmp), server)
            finally:
                server.shutdown()

    def exercise_modes(self, parent, server):
        config = json.loads(Path("configs/infobench.json").read_text(encoding="utf-8"))
        for role, model in config["models"].items():
            model.update(base_url=f"http://127.0.0.1:{server.server_port}", api_key_env=None,
                         model="test-judge" if role == "judge_a" else role)
        config_path, data = parent / "config.json", parent / "tasks.jsonl"
        write_report(config_path, config)
        tasks = [dataset.make_task(source_row(1), 42), dataset.make_task(source_row(2, "domain", 1), 42)]
        write_report(data, tasks, jsonl=True)
        official, atomic = parent / "official", parent / "atomic"

        def run(mode, output=official, more=()):
            with patch("sys.stdout"):
                main([mode, "--config", str(config_path), "--data", str(data), "--output", str(output), *more])

        run("dry-run")
        self.assertEqual(len(server.calls), 0)
        run("generate")
        self.assertEqual(len(server.calls), 4)
        kimi_request = next(call for call in server.calls if call["model"] == "candidate_b")
        self.assertEqual(kimi_request["max_completion_tokens"], 4096)
        self.assertEqual(kimi_request["reasoning_effort"], "low")
        self.assertNotIn("max_tokens", kimi_request)
        self.assertNotIn("temperature", kimi_request)
        self.assertFalse((official / "judgments.jsonl").exists())
        run("judge")
        self.assertEqual(len(server.calls), 10)
        self.assertTrue(any(len(row["messages"]) == 3 for row in server.calls))
        first = json.loads((official / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(first["candidates"]["candidate_a"]["drfr"], 1)
        run("end-to-end")
        run("aggregate")
        self.assertEqual(len(server.calls), 10)
        self.assertEqual(first, json.loads((official / "summary.json").read_text(encoding="utf-8")))
        empty = parent / "empty"
        empty.mkdir()
        run("end-to-end", atomic,
            ("--protocol", "atomic", "--resume-from", str(empty), "--resume-from", str(official)))
        self.assertEqual(len(server.calls), 16)
        self.assertTrue(all(len(row["messages"]) == 2 for row in server.calls[-6:]))
        modified = deepcopy(config)
        modified["models"]["candidate_a"]["temperature"] = 0.2
        write_report(config_path, modified)
        run("end-to-end")
        self.assertEqual(len(server.calls), 21)
