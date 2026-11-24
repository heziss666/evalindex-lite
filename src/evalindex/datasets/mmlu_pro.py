from string import ascii_uppercase


def make_task(row):
    question = row["question"]
    options = row["options"]
    choices = list(ascii_uppercase[:len(options)])
    gold = row["answer"]
    index = row["answer_index"]
    if not 0 <= index < len(choices) or choices[index] != gold:
        raise ValueError(f"Invalid option mapping for question {row['question_id']}")

    option_lines = "\n".join(f"{letter}. {option}" for letter, option in zip(choices, options))
    return {
        "id": f"mmlu-pro:{row['question_id']}",
        "source_id": row["question_id"],
        "benchmark": "MMLU-Pro",
        "category": row["category"],
        "kind": "mmlu_pro",
        "question": question,
        "options": options,
        "choices": choices,
        "gold": gold,
        "prompt": (
            "Choose the single best answer. Respond with only \"Final Answer: X\", "
            "where X is the letter of your chosen option.\n\n"
            f"{question}\n\n{option_lines}"
        ),
    }
