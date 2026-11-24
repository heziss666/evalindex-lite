import json
from unittest import TestCase

from evalindex.__main__ import summarize, validate_ids
from evalindex.datasets.math_500 import make_task as math_task
from evalindex.datasets.mmlu_pro import make_task as choice_task
from evalindex.scoring import score_task


class TestMmluPro(TestCase):
    def setUp(self):
        self.task = choice_task({
            "question_id": 7, "question": "What does this example ask?",
            "options": ["An example", "Something else", "Neither"],
            "answer": "A", "answer_index": 0, "category": "test",
            "cot_content": "private reasoning fixture",
        })

    def test_correct_option(self):
        self.assertEqual(score_task(self.task, "Final Answer: A")["score"], 1)

    def test_wrong_option(self):
        result = score_task(self.task, "Final Answer: B")
        self.assertEqual(result["score"], 0)
        self.assertTrue(result["valid"])

    def test_missing_tag(self):
        self.assertFalse(score_task(self.task, "A")["valid"])

    def test_multiple_letters(self):
        for response in ("Final Answer: A or B", "Final Answer: A\nFinal Answer: B"):
            with self.subTest(response=response):
                self.assertFalse(score_task(self.task, response)["valid"])

    def test_lowercase_option(self):
        self.assertEqual(score_task(self.task, "final answer: a")["predicted"], "A")

    def test_out_of_range_option(self):
        result = score_task(self.task, "Final Answer: D")
        self.assertEqual(result["details"]["parse_error"], "option_out_of_range")

    def test_duplicate_id(self):
        with self.assertRaisesRegex(SystemExit, "Duplicate"):
            validate_ids([self.task, self.task])

    def test_prompt_does_not_depend_on_gold(self):
        row = {
            "question_id": 7, "question": self.task["question"], "options": self.task["options"],
            "answer": "B", "answer_index": 1, "category": "test",
        }
        self.assertEqual(choice_task(row)["prompt"], self.task["prompt"])
        self.assertIn("A. An example", self.task["prompt"])
        self.assertNotIn("private reasoning fixture", self.task["prompt"])

    def test_empty_model_output(self):
        result = score_task(self.task, " ")
        self.assertEqual(result["details"]["parse_error"], "empty_response")

    def test_accuracy_includes_parse_failures(self):
        responses = ("Final Answer: A", "Final Answer: B", "")
        rows = [{**self.task, **score_task(self.task, response)} for response in responses]
        summary = summarize(rows, {})["benchmarks"]["MMLU-Pro"]
        self.assertEqual(summary["accuracy"], 1 / 3)
        self.assertEqual(summary["wrong_answers"], 1)
        self.assertEqual(summary["parse_failures"], 1)


class TestMath500(TestCase):
    def setUp(self):
        self.task = math_task({
            "unique_id": "test/example/7.json", "problem": "Compute one divided by two.",
            "answer": r"\frac{1}{2}", "solution": "Private worked solution.",
            "subject": "test", "level": 1,
        })

    def test_fraction_decimal_equivalence(self):
        result = score_task(self.task, "Final Answer: $0.5$")
        self.assertEqual(result["score"], 1)
        json.dumps(result)

    def test_wrong_number(self):
        result = score_task(self.task, "Final Answer: $7$")
        self.assertTrue(result["valid"])
        self.assertEqual(result["score"], 0)

    def test_missing_final_line(self):
        self.assertFalse(score_task(self.task, "The result is 0.5.")["valid"])

    def test_empty_delimiters(self):
        result = score_task(self.task, "Final Answer: $$")
        self.assertEqual(result["details"]["parse_error"], "unparseable_math")

    def test_prompt_excludes_solution_and_gold(self):
        self.assertIn(self.task["question"], self.task["prompt"])
        self.assertNotIn(self.task["gold"], self.task["prompt"])
        self.assertNotIn("Private worked solution.", self.task["prompt"])
