from unittest import TestCase

from evalindex.__main__ import summarize
from evalindex._vendor.ifeval import REVISION
from evalindex.analysis.badcase import collect
from evalindex.datasets.ifeval import load_rows, make_task
from evalindex.scoring import score_task


def task(key, *instructions):
    return make_task({
        "key": key, "prompt": "Follow each instruction.",
        "instruction_id_list": list(instructions), "kwargs": [{} for _ in instructions],
    })


def grade(example, response):
    return {**example, **score_task(example, response)}


class TestIFEval(TestCase):
    def test_official_set(self):
        rows = load_rows({"revision": REVISION, "split": "official"})
        self.assertEqual(len({row["key"] for row in rows}), 541)
        example = next(row for row in rows if row["key"] == 2785)
        self.assertIn("at least 3 placeholders", make_task(example)["prompt"])

    def test_strict_and_loose_multiconstraint(self):
        example = task(1, "startend:quotation", "punctuation:no_comma")
        row = grade(example, '**"Hello"**')
        self.assertEqual(row["score"], 0)
        self.assertFalse(row["details"]["prompt_strict"])
        self.assertTrue(row["details"]["prompt_loose"])
        self.assertEqual(row["details"]["instructions"], [
            {"id": "startend:quotation", "strict": False, "loose": True},
            {"id": "punctuation:no_comma", "strict": True, "loose": True},
        ])
        self.assertEqual(list(collect([row]))[0]["error_type"], "instruction_failure")

    def test_instruction_denominator_counts_each_constraint(self):
        rows = [
            grade(task(1, "startend:quotation", "punctuation:no_comma"), '**"Hello"**'),
            grade(task(2, "punctuation:no_comma"), "No, really."),
        ]
        metrics = summarize(rows, {})["benchmarks"]["IFEval"]
        self.assertEqual(metrics["prompt_level_strict"], 0)
        self.assertEqual(metrics["prompt_level_loose"], 0.5)
        self.assertEqual(metrics["instruction_level_strict"], 1 / 3)
        self.assertEqual(metrics["instruction_level_loose"], 2 / 3)

    def test_empty_response_fails_even_without_comma(self):
        row = grade(task(1, "punctuation:no_comma"), "")
        self.assertTrue(row["valid"])
        self.assertFalse(row["details"]["prompt_loose"])

    def test_repeated_language_scoring_is_consistent(self):
        example = make_task({
            "key": 1, "prompt": "Reply in English.",
            "instruction_id_list": ["language:response_language"], "kwargs": [{"language": "en"}],
        })
        response = "The students returned to school after a long summer break."
        first = grade(example, response)
        self.assertEqual(first["score"], 1)
        self.assertEqual(grade(example, response), first)

    def test_official_random_fallback_repeats_across_modes_and_runs(self):
        source = load_rows({"revision": REVISION, "split": "official"})
        example = make_task(next(row for row in source if row["key"] == 1122))
        response = "The letter yyyyy is repeated. ####"
        first = grade(example, response)
        check = first["details"]["instructions"][1]
        self.assertEqual(check["strict"], check["loose"])
        for _ in range(5):
            self.assertEqual(grade(example, response), first)

    def test_index_requires_all_dimensions_and_uses_strict(self):
        weights = {"MMLU-Pro": 1, "MATH-500": 1, "IFEval": 1}
        rows = [
            {"kind": "choice", "benchmark": "MMLU-Pro", "score": 1, "valid": True},
            {"kind": "number", "benchmark": "MATH-500", "score": 0, "valid": True},
        ]
        self.assertIsNone(summarize(rows, weights)["overall_index"])
        rows.append(grade(task(1, "startend:quotation"), '**"Hello"**'))
        self.assertAlmostEqual(summarize(rows, weights)["overall_index"], 100 / 3)
