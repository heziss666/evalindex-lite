def make_task(row):
    question = row["problem"]
    return {
        "id": f"math-500:{row['unique_id']}",
        "source_id": row["unique_id"],
        "benchmark": "MATH-500",
        "category": row["subject"],
        "level": row["level"],
        "kind": "math_500",
        "question": question,
        "gold": row["answer"],
        "prompt": (
            "Solve the problem. You may show your reasoning. End with a separate line "
            "in the form Final Answer: $<answer>$, using LaTeX for the answer.\n\n"
            f"{question}"
        ),
    }
