import json
from importlib.resources import files

from .._vendor import ifeval


def load_rows(dataset):
    if dataset["revision"] != ifeval.REVISION or dataset["split"] != "official":
        raise ValueError("IFEval configuration must match the vendored Google Research data")
    data = files(ifeval).joinpath("input_data.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def make_task(row):
    return {
        "id": f"ifeval:{row['key']}",
        "source_id": row["key"],
        "benchmark": "IFEval",
        "kind": "ifeval",
        "prompt": row["prompt"],
        "instruction_id_list": row["instruction_id_list"],
        "kwargs": row["kwargs"],
    }
