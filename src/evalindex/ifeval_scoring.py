import hashlib
from importlib.metadata import version
from threading import Lock

from ._vendor.ifeval import REVISION
from ._vendor.ifeval._random import instruction_random


LANGUAGE_SEED = 0
INSTRUCTION_SEED = 0
SCORE_LOCK = Lock()
PUNKT_FILES = ("abbrev_types.txt", "collocations.tab", "ortho_context.tab", "sent_starters.txt")


def scorer_version():
    from nltk.data import find

    try:
        english = find("tokenizers/punkt_tab/english/")
    except LookupError as exc:
        raise RuntimeError("Install IFEval tokenizer data: python -m nltk.downloader punkt_tab") from exc
    digest = hashlib.sha256()
    for name in PUNKT_FILES:
        with english.join(name).open() as stream:
            digest.update(stream.read())
    return {
        "upstream_revision": REVISION,
        "adapter": "ifeval-v1",
        "langdetect_seed": LANGUAGE_SEED,
        "instruction_seed": INSTRUCTION_SEED,
        "punkt_tab_english_sha256": digest.hexdigest(),
        "dependencies": {
            name: version(name) for name in ("absl-py", "immutabledict", "langdetect", "nltk")
        },
    }


def score_ifeval(task, response):
    from langdetect import DetectorFactory

    from ._vendor.ifeval import evaluation_lib

    instructions = task["instruction_id_list"]
    if not instructions or len(instructions) != len(task["kwargs"]):
        raise ValueError(f"Invalid IFEval instructions for {task['id']}")
    prompt = task["prompt"]
    example = evaluation_lib.InputExample(task["source_id"], instructions, prompt, task["kwargs"])
    responses = {prompt: response}
    with SCORE_LOCK:
        DetectorFactory.seed = LANGUAGE_SEED
        instruction_random.seed(INSTRUCTION_SEED)
        strict = evaluation_lib.test_instruction_following_strict(example, responses)
        instruction_random.seed(INSTRUCTION_SEED)
        loose = evaluation_lib.test_instruction_following_loose(example, responses)
    return {
        "score": int(strict.follow_all_instructions),
        "valid": True,
        "predicted": None,
        "details": {
            "prompt_strict": strict.follow_all_instructions,
            "prompt_loose": loose.follow_all_instructions,
            "instructions": [
                {"id": instruction, "strict": passed_strict, "loose": passed_loose}
                for instruction, passed_strict, passed_loose in zip(
                    instructions, strict.follow_instruction_list, loose.follow_instruction_list
                )
            ],
        },
    }


def summarize_ifeval(rows):
    details = [row["details"] for row in rows]
    instructions = [check for item in details for check in item["instructions"]]
    return {
        "prompt_level_strict": sum(item["prompt_strict"] for item in details) / len(details),
        "prompt_level_loose": sum(item["prompt_loose"] for item in details) / len(details),
        "instruction_level_strict": sum(check["strict"] for check in instructions) / len(instructions),
        "instruction_level_loose": sum(check["loose"] for check in instructions) / len(instructions),
        "instruction_count": len(instructions),
    }
