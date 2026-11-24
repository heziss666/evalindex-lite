# M1 实验报告｜IFEval 和三项综合 Index

两款 Qwen2.5-Instruct 使用官方 Q4_K_M GGUF 权重，在本机用 llama.cpp b7330 的 Windows Vulkan 构建运行。正式评测每个模型使用相同的 90 道题，MMLU-Pro、MATH-500、IFEval 各 30 道。抽样 seed 为 42，每套先跑前 5 道做冒烟。正式推理采用 zero-shot、`temperature=0`、`max_tokens=512`。

## 正式成绩

| 排名 | 模型 | MMLU-Pro Accuracy | MATH-500 Accuracy | IFEval Prompt Strict | IFEval Prompt Loose | IFEval Instruction Strict | IFEval Instruction Loose | Index / 100 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Qwen2.5-1.5B | 23.33%（7/30） | 13.33%（4/30） | 23.33%（7/30） | 23.33%（7/30） | 36.17%（17/47） | 36.17%（17/47） | 20.00 |
| 2 | Qwen2.5-0.5B | 3.33%（1/30） | 3.33%（1/30） | 26.67%（8/30） | 26.67%（8/30） | 31.91%（15/47） | 31.91%（15/47） | 11.11 |

每题的 Prompt-level 分子要求全部约束通过。Instruction-level 将每一条约束单独计数，所以本次分母是 47。Index 取 MMLU-Pro、MATH-500 和 IFEval Prompt-level Strict 的百分比等权平均。1.5B 在数学和知识题上得分较高，IFEval 中它通过了更多单条约束，0.5B 则多完整满足了一道题。

## IFEval Badcase

| 题目 | 模型 | 检查结果 |
| --- | --- | --- |
| `ifeval:1132` | 0.5B | 通过禁用词检查，正文的 “The Gifted” 使全大写检查失败。任务在长度上限结束。 |
| `ifeval:1132` | 1.5B | 通过全大写检查，但使用了题目禁用的 “ROCK”。两模型分别通过不同约束，这题的 Prompt-level 分数都为 0。 |
| `ifeval:1481` | 1.5B | 通过分节检查，未满足恰好两条 Markdown 项目符号的要求。 |

正式样本中 Strict 和 Loose 的逐约束结果相同。单测使用带 Markdown 星号的引号回复，验证 Strict 失败、Loose 去掉星号后通过的情况。

## 数据、评分器和复现

- 官方原始 IFEval 数据含 541 题、834 条约束，对应 Google Research 提交 `e6890f85757dd84e27ca6df2dd30651dafad28e0`。使用该提交原始题单，避免 Hugging Face 镜像第 2785 题的一处提示与约束参数不一致。已导出全量题单并用固定测试回复遍历、重复调用全部约束。正式推理使用其中 30 题。[Google Research 原始数据与评分器](https://github.com/google-research/google-research/tree/e6890f85757dd84e27ca6df2dd30651dafad28e0/instruction_following_eval) · [Hugging Face 镜像](https://huggingface.co/datasets/google/IFEval/blob/966cd89545d6b6acfd7638bc708b98261ca58e84/ifeval_input_data.jsonl)
- 移植保留官方 Strict 与 Loose 检查。官方 `LetterFrequencyChecker` 会对非英文字母参数随机回退，全量中涉及 `ifeval:1122`（`#`）与 `ifeval:1129`（`!`）。本项目给两种检查固定同一个回退 seed 0，并固定语言检测 seed 0。这两题均未抽入正式子集。复现整套分数时需沿用这些种子。[官方 LetterFrequencyChecker](https://github.com/google-research/google-research/blob/e6890f85757dd84e27ca6df2dd30651dafad28e0/instruction_following_eval/instructions.py#L1314)
- 正式运行使用本地提交 `c64bd5faf43d86bfde2d55e6df9910195a0849bb`。后续提交 `97c23f0` 固定了打包时原始题库的换行格式。Python 3.13.9，依赖 `absl-py 2.3.1`、`immutabledict 4.2.1`、`langdetect 1.0.9`、`nltk 3.9.2` 与 `punkt_tab`。英文分句资源哈希、其余数据集 revision、模型 revision 见两份正式 `summary.json`。
- 28 项测试通过，原有 Demo Replay 综合分仍为 83.33。两个模型的 180 条正式回复均已 Replay，逐题结果、错误样本、指标及 Index 与对应的正式运行一致。

## 修改文件

| 位置 | 用途 |
| --- | --- |
| `src/evalindex/_vendor/ifeval/`、`datasets/ifeval.py`、`datasets/__main__.py` | 固定官方数据和源码，导出全量或抽样题单。 |
| `src/evalindex/ifeval_scoring.py`、`scoring.py`、`analysis/badcase.py`、`__main__.py` | 调用两种检查，记录逐约束结果，汇总四项指标并输出错误样本。 |
| `src/evalindex/compare.py`、`configs/benchmarks.json`、`configs/index_weights.json` | 声明数据版本和指数权重，比较题单、协议和评分器的可比性。 |
| `pyproject.toml`、`README.md`、`tests/test_ifeval.py`、`tests/test_compare.py` | 固定依赖，记录复现命令，覆盖聚合、Strict/Loose 差异、缺失维度、重复评分与比较检查。 |

## 局限

正式推理每个数据集仅 30 题。IFEval 中 0.5B 有 15 道、1.5B 有 6 道达到 512 token 上限。分数反映这次的子集、量化和输出预算。IFEval 检查的是题目注册的可验证约束，主题相关性和答案质量超出本次指标覆盖范围。综合 Index 采用本项目等权定义。

排行榜由评测命令生成到本地 `runs/m1/leaderboard.json`，两份正式摘要位于 `runs/m1/tasks/<模型>/summary.json`。[复现命令](../README.md#运行-ifeval-和三项综合-index)
