# EvalIndex Lite — 可运行的多维 LLM 评测项目脚手架

> EvalIndex Lite 已接入 MMLU-Pro、MATH-500 和 IFEval，支持 zero-shot 抽样、真实推理和 Replay 复评分。演示输入集中在 `tests/fixtures/demo/`。

[当前 M1 实验报告](docs/m1-ifeval-report.md)

## 目标

对多个模型以统一数据、版本、采样协议完成批量推理，并将推理结果交给 benchmark-specific 评分器：MMLU-Pro（选项正确率）、MATH-500（数学等价）、IFEval（官方 Strict/Loose 约束检查）、自建知识工作任务（Atomic Rubric / Pairwise Judge / Crowd-BT），最终生成细分指标、综合指数、置信区间和 Badcase。注意自定义指数不等于 AA 官方指数。

## 立刻运行（不需要 GPU、不需要 API Key）

```powershell
python -m pip install -e ".[benchmarks]"
$demoOutput = Join-Path ([IO.Path]::GetTempPath()) 'evalindex-replay-demo'
python -m evalindex --data tests/fixtures/demo/tasks.jsonl --replay tests/fixtures/demo/predictions.jsonl --weights tests/fixtures/demo/weights.json --output $demoOutput
python -m unittest discover -s tests -v
```

临时目录 `$demoOutput` 包含 `results.jsonl`（逐条结果）和 `summary.json`（分项、指数）。这是 **Replay 模式**，它只测试评测管线，不调用模型。

## 真正调用模型

先启动支持 OpenAI Chat Completions API 的服务（例如 vLLM），或配置你已有的 OpenAI-compatible 端点。然后：

```bash
export EVAL_BASE_URL=http://localhost:8000/v1
export EVAL_API_KEY=your-key-if-needed
python -m evalindex --data tests/fixtures/demo/tasks.jsonl --model YOUR_MODEL_ID --weights tests/fixtures/demo/weights.json --output runs/my-model
```

**参数注意**：默认 temperature=0、max_tokens=1024；不同模型/推理端点可能不支持同样的采样参数，需根据模型调整并在报告中记录。`YOUR_MODEL_ID` 应当与服务端注册的 model id 一致。不要把 API Key 提交到仓库。

## 启动本地模型服务

启动兼容 OpenAI Chat Completions 的服务。把服务地址和模型 ID 换成实际值，鉴权密钥如有需要可通过 `EVAL_API_KEY` 环境变量提供。以下示例使用两个端口，每个端口服务一个模型。

本次运行使用 [llama.cpp b7330 的 Windows Vulkan 构建](https://github.com/ggml-org/llama.cpp/releases/tag/b7330)，权重为两个官方 Q4_K_M GGUF 文件。[Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/blob/9217f5db79a29953eb74d5343926648285ec7e67/qwen2.5-0.5b-instruct-q4_k_m.gguf) · [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/blob/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf)

将对应 GGUF 放在工作目录，在两个终端各启动一个服务。

```powershell
.\llama-server.exe -m qwen2.5-0.5b-instruct-q4_k_m.gguf --alias qwen2.5-0.5b-instruct-q4_k_m --host 127.0.0.1 --port 18080 -ngl 99 -c 4096 -np 1
.\llama-server.exe -m qwen2.5-1.5b-instruct-q4_k_m.gguf --alias qwen2.5-1.5b-instruct-q4_k_m --host 127.0.0.1 --port 18081 -ngl 99 -c 4096 -np 1
```

```powershell
$cfg = Get-Content -Raw configs/benchmarks.json | ConvertFrom-Json
$models = @(
    @{ id = 'qwen2.5-0.5b-instruct-q4_k_m'; url = 'http://127.0.0.1:18080/v1'; revision = '9217f5db79a29953eb74d5343926648285ec7e67' },
    @{ id = 'qwen2.5-1.5b-instruct-q4_k_m'; url = 'http://127.0.0.1:18081/v1'; revision = '91cad51170dc346986eccefdc2dd33a9da36ead9' }
)
```

每次运行生成 `results.jsonl`（原始输出、参考答案、解析结果、分数、结束原因）、`summary.json`（各数据集 Accuracy、解析失败计数及原因、运行元数据）和 `badcases.jsonl`（答错和解析失败的逐题记录）。使用已保存输出复评分时，可将模型参数换成 `--replay runs/<模型>/results.jsonl`，并使用新的输出目录。

MMLU-Pro 要求输出单行 `Final Answer: X`，字母大小写均可。MATH-500 提示只输出一行 LaTeX 答案，评分器从最后一行 `Final Answer:` 提取表达式，再用 Math-Verify 判定与参考答案是否等价。两个数据集都将解析失败计为 0 分，并保留在 Accuracy 的分母中。题目及选项进入模型请求，参考答案留在评分端。30 题抽样分数仅适用于本次协议。

## 运行 IFEval 和三项综合 Index

IFEval 随项目提供 Google Research 原始 541 道题和官方评分器，固定在同一提交。源文件保留 Apache 2.0 许可与版权信息。移植修改了包导入，并给语言检测和官方约束的随机回退固定 seed 0。评测发送原始 prompt，汇总记录评分器提交、依赖版本与 NLTK 英文分句数据哈希。[官方数据与评分器](https://github.com/google-research/google-research/tree/e6890f85757dd84e27ca6df2dd30651dafad28e0/instruction_following_eval)

```powershell
python -m pip install -e ".[benchmarks]"
python -m nltk.downloader punkt_tab
python -m evalindex.datasets --count 30 --smoke-count 5
```

导出命令以 seed 42 从三个数据集无放回各抽 30 题，并从每个子集取前 5 题作为冒烟题。沿用上一节模型服务和 PowerShell 的 `$models`、`$cfg`，依次跑冒烟、正式评测和排行。

如需临时查看全量 IFEval，可运行 `python -m evalindex.datasets --benchmarks IFEval --count 541 --output (Join-Path ([IO.Path]::GetTempPath()) 'evalindex-ifeval-full')`。

```powershell
foreach ($stage in 'smoke', 'tasks') {
    foreach ($model in $models) {
        python -m evalindex --model $model.id --base-url $model.url --model-revision $model.revision --temperature $cfg.temperature --max-tokens $cfg.max_tokens --data "data/benchmarks/m1/$stage.jsonl" --output "runs/m1/$stage/$($model.id)"
        if ($LASTEXITCODE -ne 0) { throw "Evaluation failed for $($model.id) at $stage" }
    }
}
$summaries = @($models | ForEach-Object { "runs/m1/tasks/$($_.id)/summary.json" })
python -m evalindex.compare @summaries --out runs/m1/leaderboard.json
```

| IFEval 指标 | 分子 | 分母 |
| --- | --- | --- |
| Prompt-level Strict | 所有约束在原始回复上都通过的题数 | 总题数 |
| Prompt-level Loose | 所有约束都通过官方宽松检查的题数 | 总题数 |
| Instruction-level Strict | 在原始回复上通过的约束数 | 总约束数 |
| Instruction-level Loose | 通过官方宽松检查的约束数 | 总约束数 |

Loose 对每条约束尝试原始文本及官方规定的变体，包括去掉星号、去掉首行或末行。各约束可以在不同变体上通过。`results.jsonl` 保存逐约束的 Strict 和 Loose 布尔值。Strict 失败的题进入 `badcases.jsonl`，其中还能看出哪些约束在 Loose 下通过。

默认题单是 `data/benchmarks/m1/tasks.jsonl`，默认权重是 `configs/index_weights.json`。综合 Index 是 MMLU-Pro Accuracy、MATH-500 Accuracy 和 IFEval Prompt-level Strict 的平均值乘 100。缺少任一维度时 `overall_index` 为 `null`。排行榜要求真实运行的题单哈希、数据集版本、抽样与提示设置、评分器版本、生成协议和权重一致。旧版真实结果需要重新运行以补齐协议元数据。

使用正式原始响应做 Replay 时，保留原题单和同一权重配置。

```powershell
$replayOutput = Join-Path ([IO.Path]::GetTempPath()) 'evalindex-replay-0.5b'
python -m evalindex --replay runs/m1/tasks/qwen2.5-0.5b-instruct-q4_k_m/results.jsonl --output $replayOutput
```

## 代码结构

```text
src/evalindex/
  __main__.py    # 批处理运行、保存逐题结果与摘要
  model.py       # OpenAI-compatible HTTP adapter
  scoring.py     # 演示用选择题、数值题、指令约束评分
  benchmark_scoring.py
  ifeval_scoring.py
  datasets/     # 加载、抽样与题目构造
  _vendor/ifeval/ # 官方 IFEval 数据与评分器
  analysis/     # 错误样本与解析失败统计
configs/
  benchmarks.json
  index_weights.json
data/benchmarks/ # 导出的正式题单和冒烟题单
docs/            # 实验报告与历史任务说明
runs/            # 逐题结果、汇总和排行榜
tests/
  fixtures/demo/ # 演示题目、两套回答和演示权重
  test_scoring.py
```

## 重要设计原则

- 数据加载与模型推理分离；模型请求不能包含 gold、Rubric 判定答案。
- 所有原始模型输出须保存，支持不重新推理就重跑评分器（Replay/Audit）。
- 数据集 `id` 必须唯一；至少记录数据集版本/哈希、模型版本、配置、Prompt 模板、输出长度和时间。
- 解析失败应按预先声明的政策处理；本演示将无法解析答案视为该题 0 分，并另外记录 `valid=false`。
- 演示 `number` 支持普通数值及简单分数。MATH-500 使用 `math_verify` 判定数学等价。
- 演示 `constraints` 使用基本字符串规则。IFEval 调用官方 Strict 与 Loose 检查器。
- `rubric` 类型目前显式返回 `score=null`；未连接、未校准 Judge 时不得假装已有得分。
- 综合分数需有明确且固定权重，必须同时报告各维度分数。缺失任一规定维度时不输出整体 Index。
- 公开测试集可能存在数据污染；只将独立、同协议的结果用于模型比较。

## 建议迭代顺序（每步都能形成可检查交付物）

1. **M0：运行链路（当前）**：Replay → 单元测试 → 本地/API 模型端点。
2. **M1：真实客观评测**：引入 MMLU-Pro（先抽样 30 题，再 100 题），保留选项映射、生成解析与解析失败原因；MATH-500 接入 Math-Verify；IFEval 接入官方 Strict/Loose 评分器，并保留其 4 个指标。
3. **M2：Judge 校准**：自建 30–50 个任务，Atomic Rubric（5–8 项/题）；至少两名人工对 30 份回答复审，计算 Judge-vs-Human Agreement 与误判案例；Judge 输出结构化 verdict 和 reason。
4. **M3：Pairwise & 排名**：对相同题目的两个模型输出成对比较，正反位置测试，计算 Win/Tie/Loss，先实现 Bradley–Terry，之后才考虑 Crowd-BT；综合指数采用预定义权重，排名报告提供置信区间。
5. **M4：报告界面**：用 Streamlit 或其他前端查看模型对比、分科成绩、Badcase、成本/延迟、Prompt/配置、Judge 分歧。

## 验收清单

- [ ] 同一模型同一 Prompt 结果可追溯（原始输出和环境参数保存）
- [ ] Replay 不需要重新消耗 Token 就能重跑评分器
- [ ] 解析失败单独统计；绝不静默删题以提高 Accuracy
- [ ] 不同模型使用完全相同的题集版本与评分器
- [ ] 对比的分数有基本配对分析与置信区间
- [ ] 至少 20 条 Badcase 归因与 1 次评分器误判修复记录
- [ ] README 写清楚自建 Index 与 AA 官方 Intelligence Index 的区别

## 官方参考

- https://artificialanalysis.ai/methodology/intelligence-benchmarking
- https://github.com/TIGER-AI-Lab/MMLU-Pro
- https://huggingface.co/datasets/HuggingFaceH4/MATH-500
- https://github.com/google-research/google-research/tree/master/instruction_following_eval
- https://github.com/huggingface/Math-Verify
- https://github.com/EleutherAI/lm-evaluation-harness
- https://inspect.aisi.org.uk/scoring.html

## 对比两个 Replay 模型，生成排行榜

```bash
python -m evalindex --data tests/fixtures/demo/tasks.jsonl --replay tests/fixtures/demo/predictions.jsonl --weights tests/fixtures/demo/weights.json --output runs/model-a
python -m evalindex --data tests/fixtures/demo/tasks.jsonl --replay tests/fixtures/demo/predictions_model_b.jsonl --weights tests/fixtures/demo/weights.json --output runs/model-b
python -m evalindex.compare runs/model-a/summary.json runs/model-b/summary.json --out runs/leaderboard.json
```

`compare` 检查两个运行的数据文件哈希与指数权重是否一致；不一致则拒绝直接排名。Replay 的模型名默认为 `REPLAY_FIXTURE`，因此两个结果会使用相同标签；使用真实模型时，分别指定 `--model` 即可保留模型 ID。
