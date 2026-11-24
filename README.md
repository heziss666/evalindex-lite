# EvalIndex Lite — 可运行的多维 LLM 评测项目脚手架

> EvalIndex Lite 已接入真实 MMLU-Pro 与 MATH-500 题库，使用本项目的 zero-shot 抽样协议。`data/demo_*` 用于验证 Replay 链路。

## 目标

对多个模型以统一数据、版本、采样协议完成批量推理，并将推理结果交给 benchmark-specific 评分器：MMLU-Pro（选项正确率）、MATH-500（数学等价）、IFEval（官方 Strict/Loose 约束检查）、自建知识工作任务（Atomic Rubric / Pairwise Judge / Crowd-BT），最终生成细分指标、综合指数、置信区间和 Badcase。注意自定义指数不等于 AA 官方指数。

## 立刻运行（不需要 GPU、不需要 API Key）

```bash
python -m pip install -e ".[benchmarks]"
python -m evalindex --data data/demo_tasks.jsonl --replay data/demo_predictions.jsonl --output runs/replay-demo
python -m unittest discover -s tests -v
```

输出：`runs/replay-demo/results.jsonl`（逐条结果）和 `summary.json`（分项、指数）。这是 **Replay 模式**，它只测试评测管线，不调用模型。

## 真正调用模型

先启动支持 OpenAI Chat Completions API 的服务（例如 vLLM），或配置你已有的 OpenAI-compatible 端点。然后：

```bash
export EVAL_BASE_URL=http://localhost:8000/v1
export EVAL_API_KEY=your-key-if-needed
python -m evalindex --data data/demo_tasks.jsonl --model YOUR_MODEL_ID --output runs/my-model
```

**参数注意**：默认 temperature=0、max_tokens=1024；不同模型/推理端点可能不支持同样的采样参数，需根据模型调整并在报告中记录。`YOUR_MODEL_ID` 应当与服务端注册的 model id 一致。不要把 API Key 提交到仓库。

## 运行 MMLU-Pro 和 MATH-500

在项目目录执行以下 PowerShell 命令。安装额外依赖后，从固定的 Hugging Face revision 下载两套题库的 `test` split。使用 seed 42 无放回各取 30 题，另将每套的前 5 题保存为冒烟子集。

```powershell
python -m pip install -e ".[benchmarks]"
python -m unittest discover -s tests -v
python -m evalindex.datasets --count 30 --smoke-count 5
```

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
foreach ($model in $models) {
    $sample = @('--model', $model.id, '--base-url', $model.url, '--model-revision', $model.revision,
                '--temperature', $cfg.temperature, '--max-tokens', $cfg.max_tokens)
    python -m evalindex @sample --data data/benchmarks/smoke.jsonl --output "runs/smoke-$($model.id)"
    if ($LASTEXITCODE -ne 0) { throw "Smoke test failed for $($model.id)" }
}
foreach ($model in $models) {
    $sample = @('--model', $model.id, '--base-url', $model.url, '--model-revision', $model.revision,
                '--temperature', $cfg.temperature, '--max-tokens', $cfg.max_tokens)
    python -m evalindex @sample --data data/benchmarks/tasks.jsonl --output "runs/$($model.id)"
    if ($LASTEXITCODE -ne 0) { throw "Evaluation failed for $($model.id)" }
}
```

每次运行生成 `results.jsonl`（原始输出、参考答案、解析结果、分数、结束原因）、`summary.json`（各数据集 Accuracy、解析失败计数及原因、运行元数据）和 `badcases.jsonl`（答错和解析失败的逐题记录）。使用已保存输出复评分时，可将模型参数换成 `--replay runs/<模型>/results.jsonl`，并使用新的输出目录。

MMLU-Pro 要求输出单行 `Final Answer: X`，字母大小写均可。MATH-500 从最后一行 `Final Answer:` 提取表达式，再用 Math-Verify 判定与参考答案是否等价。两个数据集都将解析失败计为 0 分，并保留在 Accuracy 的分母中。题目及选项进入模型请求，参考答案留在评分端。30 题抽样分数仅适用于本次协议。

## 代码结构

```text
src/evalindex/
  __main__.py    # 批处理运行、保存逐题结果与摘要
  model.py       # OpenAI-compatible HTTP adapter
  scoring.py     # 演示用选择题、数值题、指令约束评分
  benchmark_scoring.py
  datasets/     # 两个数据集的加载、抽样与题目构造
  analysis/     # 错误样本与解析失败统计
configs/
  index_weights.json
 data/
   demo_tasks.jsonl
   demo_predictions.jsonl
 tests/
   test_scoring.py
```

## 重要设计原则

- 数据加载与模型推理分离；模型请求不能包含 gold、Rubric 判定答案。
- 所有原始模型输出须保存，支持不重新推理就重跑评分器（Replay/Audit）。
- 数据集 `id` 必须唯一；至少记录数据集版本/哈希、模型版本、配置、Prompt 模板、输出长度和时间。
- 解析失败应按预先声明的政策处理；本演示将无法解析答案视为该题 0 分，并另外记录 `valid=false`。
- 演示 `number` 只支持普通数值及简单分数，不支持 LaTeX、集合和符号表达式。正式 MATH-500 请接入 `math_verify` 并做反例验证。
- 演示 `constraints` 只实现基本字符串规则。正式 IFEval 必须调用官方检查器，不能把这些规则称为 IFEval 分数。
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
python -m evalindex --data data/demo_tasks.jsonl --replay data/demo_predictions.jsonl --output runs/model-a
python -m evalindex --data data/demo_tasks.jsonl --replay data/demo_predictions_model_b.jsonl --output runs/model-b
python -m evalindex.compare runs/model-a/summary.json runs/model-b/summary.json --out runs/leaderboard.json
```

`compare` 检查两个运行的数据文件哈希与指数权重是否一致；不一致则拒绝直接排名。Replay 的模型名默认为 `REPLAY_FIXTURE`，因此两个结果会使用相同标签；使用真实模型时，分别指定 `--model` 即可保留模型 ID。
