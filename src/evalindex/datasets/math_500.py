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
            "Solve the problem. Reply with just one line starting with Final Answer: "
            "and put your final result in LaTeX after the colon. Do not include your working.\n\n"
            f"{question}"
        ),
    }
