import json
import tempfile
import unittest
from pathlib import Path
from evalindex.compare import compare

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
