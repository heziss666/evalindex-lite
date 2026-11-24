import json
import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from evalindex.compare import check_compatibility, compare

class TestCompare(unittest.TestCase):
    def test_compare_sorts_scores_and_checks_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = Path(d)/"a.json"
            p2 = Path(d)/"b.json"
            common={"scored": 6, "total": 6, "benchmarks":{"demo":{"score":1}}, "run":{"data_sha256":"sha","weights":{"demo":1}}}
            a=json.loads(json.dumps(common)); a["overall_index"]=80; a["run"]["model"]="a"
            b=json.loads(json.dumps(common)); b["overall_index"]=90; b["run"]["model"]="b"
            p1.write_text(json.dumps(a)); p2.write_text(json.dumps(b))
            self.assertEqual(compare([p1,p2])["leaderboard"][0]["model"],"b")
            b["run"]["data_sha256"]="different"
            p2.write_text(json.dumps(b))
            with self.assertRaises(ValueError):compare([p1,p2])

    def test_real_comparison_checks_protocol_and_provenance(self):
        common = {
            "benchmarks": {"IFEval": 0.5}, "mode": "live", "data_sha256": "same",
            "datasets": {"IFEval": {
                "repository": "source", "revision": "rev", "split": "official",
                "prompt_version": "prompt", "subset_seed": 42, "shots": 0,
            }},
            "scorers": {"IFEval": {"adapter": "ifeval-v1"}},
            "protocol": {"inference": "chat-completions-v1", "temperature": 0, "max_tokens": 512},
            "weights": {"IFEval": 1},
        }
        check_compatibility([common, deepcopy(common)])
        for field, change in (
            ("datasets", {"revision": "different"}),
            ("scorers", {"adapter": "different"}),
            ("protocol", {"max_tokens": 256}),
            ("weights", 2),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                other = deepcopy(common)
                if field in {"datasets", "scorers"}:
                    other[field]["IFEval"].update(change)
                elif field == "protocol":
                    other[field].update(change)
                else:
                    other[field]["IFEval"] = change
                check_compatibility([common, other])
        with self.assertRaisesRegex(ValueError, "metadata"):
            check_compatibility([{**common, "scorers": None}])
