import hashlib
import json
import random
from collections import defaultdict
from urllib.request import urlopen


REPOSITORY = "kqsong/InFoBench"
REVISION = "cef03a2830944bfb0d201107895ddd0e0e90bf0e"
SOURCE_SHA256 = "66a2ee8d70208a7a879a17f471ba0ffd097b698265ea4796be99a273fdcc6559"
SOURCE_URL = f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/InfoBench.json"


def read_source(raw):
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("InFoBench source SHA-256 does not match the pinned revision")
    return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]


def load_rows(source=None):
    if source is not None:
        return read_source(source.read_bytes())
    with urlopen(SOURCE_URL, timeout=45) as response:
        return read_source(response.read())


def make_task(row, seed):
    source_id = row["id"]
    if not isinstance(source_id, str):
        raise ValueError("InFoBench task ID must be a string")
    task_type, separator, _ = source_id.partition("_oriented_task_")
    if not separator or task_type not in {"user", "domain"} or row["subset"] not in {"Easy_set", "Hard_set"}:
        raise ValueError(f"Invalid InFoBench task identity: {source_id}")
    fields = ("instruction", "input", "category")
    if any(not isinstance(row[key], str) for key in fields) or not row["instruction"].strip():
        raise ValueError(f"Invalid InFoBench task text: {source_id}")
    questions, labels = row["decomposed_questions"], row["question_label"]
    if (not isinstance(questions, list) or not isinstance(labels, list) or not questions
            or len(questions) != len(labels)
            or any(not isinstance(q, str) or not q.strip() for q in questions)
            or any(not isinstance(group, list) or any(not isinstance(label, str) for label in group)
                   for group in labels)):
        raise ValueError(f"Invalid requirements for {source_id}")
    task_id = f"infobench:{source_id}"
    return {
        "id": task_id, "source_id": source_id, "kind": "infobench", "benchmark": "InFoBench",
        **{key: row[key] for key in fields},
        "subset": row["subset"], "task_type": task_type,
        "prompt": row["instruction"] + ("\n\n" + row["input"] if row["input"] else ""),
        "requirements": [
            {"id": f"{task_id}:r{index}", "question": question, "labels": tag_list}
            for index, (question, tag_list) in enumerate(zip(questions, labels), 1)
        ],
        "dataset": {
            "repository": REPOSITORY, "revision": REVISION, "split": "test",
            "source_sha256": SOURCE_SHA256, "seed": seed,
            "sampling": "type-category-round-robin-v1", "prompt_version": "instruction-input-v1",
        },
    }


def sample_tasks(rows, count, seed):
    groups = defaultdict(lambda: defaultdict(list))
    seen = set()
    for row in rows:
        task = make_task(row, seed)
        if task["id"] in seen:
            raise ValueError(f"Duplicate InFoBench task: {task['id']}")
        seen.add(task["id"])
        groups[task["task_type"]][task["category"]].append(task)
    if not 1 <= count <= len(seen):
        raise ValueError(f"Expected sample count between 1 and {len(seen)}")
    rng = random.Random(seed)
    pools = {}
    for task_type, groups_by_category in sorted(groups.items()):
        categories = sorted(groups_by_category)
        rng.shuffle(categories)
        for items in groups_by_category.values():
            rng.shuffle(items)
        pools[task_type] = [
            groups_by_category[category][index]
            for index in range(max(map(len, groups_by_category.values())))
            for category in categories if index < len(groups_by_category[category])
        ]
    ordered = [
        pool[index] for index in range(max(map(len, pools.values())))
        for pool in pools.values() if index < len(pool)
    ]
    return ordered[:count]
