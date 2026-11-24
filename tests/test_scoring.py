import unittest
from evalindex.scoring import score_task, extract_choice

class TestScoring(unittest.TestCase):
    def test_choice_uses_final_answer_not_first_letter(self):
        task={"kind":"choice","gold":"B","choices":["A","B","C","D"]}
        result=score_task(task,"A 不正确。\nFinal Answer: B")
        self.assertEqual(result["score"],1)
    def test_number_fraction_equivalence(self):
        self.assertEqual(score_task({"kind":"number","gold":"0.5"},"Final Answer: 1/2")["score"],1)
    def test_constraints_allpass(self):
        task={"kind":"constraints","rules":[{"type":"contains","value":"模型"},{"type":"endswith","value":"END"}]}
        self.assertEqual(score_task(task,"模型 OK")["score"],0)
        self.assertEqual(score_task(task,"模型 OK END")["score"],1)
    def test_rubric_never_fakes_score(self):
        result=score_task({"kind":"rubric"},"whatever")
        self.assertIsNone(result["score"])

if __name__ == "__main__": unittest.main()
