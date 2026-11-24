# M2 · InFoBench 与 LLM Judge

当前 Candidate B 暂用 Kimi K3.1 Pro，已完成与 Qwen 的 5 题真实冒烟及 30 题正式评测。

## 配置 API Key

在项目根目录运行以下 PowerShell 命令。现有 `.env` 会保留。

```powershell
if (!(Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
code .env
```

当前配置读取 Qwen、Kimi、DeepSeek 三把密钥。已有 Qwen 和 DeepSeek 配置时，只需填写 `MOONSHOT_API_KEY=你的密钥`，也可在当前终端提供同名环境变量。环境变量优先于 `.env`。`.env` 已被 Git 忽略，模型和接口参数在 `configs/infobench.json` 调整。[Moonshot API Key 管理](https://platform.kimi.com/console/api-keys)

| 角色 | 模型 ID | Base URL | `.env` 变量 |
| --- | --- | --- | --- |
| Candidate A | `qwen3.7-flash-2026-07-15` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` |
| Candidate B | `kimi-k3.1-pro` | `https://api.moonshot.cn/v1` | `MOONSHOT_API_KEY` |
| Judge A | `deepseek-v4-pro` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |

Qwen 示例对应百炼北京按量付费，使用同地域 Key。Base URL 由客户端追加 `/chat/completions`。Qwen 和 DeepSeek 关闭思考，输出上限分别为 2,048 和 256 tokens。Kimi K3.1 Pro 始终开启思考，使用 `reasoning_effort: low` 和 `max_completion_tokens: 4096`，由服务端使用固定采样参数。默认并发为 1。[百炼接口](https://help.aliyun.com/zh/model-studio/base-url) · [Kimi API 参数](https://platform.kimi.com/docs/guide/kimi-k3-1-pro-quickstart) · [DeepSeek 接口](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)

需要恢复 GLM 时，在命令里加 `--candidate-b glm`。该配置使用原来的 `BIGMODEL_API_KEY` 和原运行目录。[智谱模型与接口](https://docs.bigmodel.cn/cn/guide/models/free/glm-4.7-flash)

## 费用估算

Kimi K3.1 Pro 普速版每百万 Token 未命中输入 ¥13、缓存命中输入 ¥1.30、输出 ¥68。按每题平均 1,200 输出 tokens 估算，Kimi 生成部分约 ¥0.41 / 5 题、¥2.48 / 30 题，另计新增的 Judge 调用、重试和缓存写入费。[Kimi 官方单价](https://www.kimi.com/news/kimi-k3-1-pro) · [缓存计费](https://platform.kimi.com/docs/pricing/chat)

北京百炼短输入档 Qwen 约 ¥0.20 输入和 ¥0.80 输出。DeepSeek V4 Pro 每百万 Token 高峰为 ¥9.00 未缓存输入、¥0.30 缓存命中输入和 ¥27.00 输出，空闲时段单价减半。项目的 `dry-run` 按配置单价估算整轮请求，不扣减可复用的调用和缓存。下文分别记录两次真实运行的新增费用。[百炼价格](https://help.aliyun.com/zh/model-studio/model-pricing) · [DeepSeek 价格与时段](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

## 真实冒烟结果

2026-11-24 晚间（北京时间）使用 `official` 协议、原来的固定 5 题和 DeepSeek V4 Pro。复用 Qwen 的 5 份回答和 22 条判分，新增 Kimi 的 5 份回答和 22 条判分。两边评分覆盖率均为 100%。

| 候选模型 | DRFR | Prompt-level Mean Pass | Prompt-level All-pass |
| --- | ---: | ---: | ---: |
| Qwen3.7 Flash | 86.36%（19/22） | 85.0% | 60.0%（3/5） |
| Kimi K3.1 Pro | 90.91%（20/22） | 87.5% | 60.0%（3/5） |

Kimi 共发出 13 次请求，5 次成功、6 次 HTTP 429、2 次超时。第一次完成 3 题，冷却后续跑补齐另外 2 题。客户端延长了 Kimi 429 退避，保留已知的错误类型，并对明确的配额耗尽停止重试。44 条 Judge 回复均成功解析，候选与 Judge 成功输出均未截断。这 5 题用于验证链路，Judge 判分准确性仍待人工复核。[Kimi API 错误类型](https://platform.kimi.com/docs/api/errors)

| 新增调用 | API 请求 | 已报告输入 tokens | 已报告输出 tokens | 估算费用 |
| --- | ---: | ---: | ---: | ---: |
| Kimi 生成 | 13 | 750 | 5,072 | ¥0.355 |
| DeepSeek Judge | 22 | 17,190 | 22 | ¥0.025 |
| 合计 | 35 | 17,940 | 5,094 | ¥0.379 |

DeepSeek 输入中 12,160 tokens 命中缓存，按空闲时段单价估算。Kimi 的 2,517 个思考 tokens 已含在输出 tokens 中。8 次失败请求未上报用量，估算未计入这些请求，结算以平台账单为准。原始推理、逐要求评分与错误样本在本地 `runs/m2/smoke/official-kimi/`。离线重聚合发出 0 次 API 请求，五个产物均与保存版本逐字节一致。[Kimi 单价](https://www.kimi.com/news/kimi-k3-1-pro) · [DeepSeek 缓存与时段单价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

## 30 题正式评测

2026-11-24 20:44–21:05（北京时间）使用 `official` 协议。两位候选使用同一份固定题单，每个候选 30 题、129 条要求。题单 SHA-256 为 `b567c1a0b09e0dd4131e12d64d73717ea9fe2fdcfa6258db40e13dfc8a4e2c19`。

| 候选模型 | 生成覆盖 | 评分覆盖 | DRFR | Prompt-level Mean Pass | Prompt-level All-pass |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3.7 Flash | 30/30 | 100%（129/129） | 82.17%（106/129） | 81.36% | 56.67%（17/30） |
| Kimi K3.1 Pro | 30/30 | 100%（129/129） | 91.47%（118/129） | 91.80% | 70.00%（21/30） |

本轮复用 Qwen 已有的 30 份正式回答和 129 条判分，以及 Kimi 冒烟的 5 份回答和 22 条判分。Kimi 新生成 25 份回答，全程单并发，新题之间等待 15 秒。其中一次请求在约 120 秒超时，重试后约 110 秒返回。正式阶段无新增 HTTP 429。Kimi 无截断，Qwen 有 3 份回答达到输出上限，按已返回的文本评判。

DeepSeek V4 Pro 给两位候选合计完成 258 条判分，解析失败为 0。`badcases.jsonl` 记录 Kimi 的 11 条未通过要求、Qwen 的 23 条未通过要求和 3 条回答截断记录。`human_review.jsonl` 保留 20 条待人工复核的判分。本次成绩来自 30 道抽样题和自动判分。

| 新增调用 | API 请求 | 已报告输入 tokens | 已报告输出 tokens | 估算费用 |
| --- | ---: | ---: | ---: | ---: |
| Kimi 生成 | 26 | 3,825 | 18,580 | ¥1.313 |
| DeepSeek Judge | 107 | 77,520 | 107 | ¥0.111 |
| 合计 | 133 | 81,345 | 18,687 | ¥1.424 |

DeepSeek 本轮新增输入中 55,040 tokens 命中缓存，按空闲时段单价估算。Kimi 的 7,742 个思考 tokens 已含在输出 tokens 中。一次超时未上报用量，未计入估算。Kimi 冒烟和正式阶段合计新增约 ¥1.803，复用记录的历史费用另计。结算以平台账单为准。[Kimi 单价](https://www.kimi.com/news/kimi-k3-1-pro) · [DeepSeek 价格与时段](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

正式产物在本地 `runs/m2/tasks/official-kimi/`。离线重聚合发出 0 次 API 请求，五个产物与保存版本逐字节一致。

## 命令

已安装 EvalIndex Lite 的 Python 环境即可运行 M2，M2 不额外依赖第三方 SDK。

```powershell
python -m evalindex.infobench export
python -m evalindex.infobench dry-run
python -m evalindex.infobench dry-run --data data/benchmarks/m2/tasks.jsonl
```

导出生成正式题单、冒烟题单和含 SHA-256、任务类型、类别分布的 `manifest.json`。可用 `--count` 改导出数，或用 `--source` 提供一份相同 SHA-256 的离线原始文件。

填入密钥后，冒烟可一步完成。

```powershell
python -m evalindex.infobench end-to-end --resume-from runs/m2/tasks/official-kimi
```

已有正式结果时，以上命令会复用匹配的回答和判分，冒烟结果保存在 `runs/m2/smoke/official-kimi/`。也可分开执行。

```powershell
python -m evalindex.infobench generate --resume-from runs/m2/tasks/official-kimi
python -m evalindex.infobench judge --resume-from runs/m2/tasks/official-kimi
python -m evalindex.infobench aggregate
```

用冒烟生成的回答做少量结构化 Judge 验证时，从原运行复用候选回答。

```powershell
python -m evalindex.infobench judge --protocol atomic --resume-from runs/m2/smoke/official-kimi
```

确认正式预算后运行下列命令。相同题目、模型配置、回复和评分提示的成功记录会复用。重复执行同一命令可续跑。

```powershell
python -m evalindex.infobench end-to-end --data data/benchmarks/m2/tasks.jsonl --resume-from runs/m2/smoke/official-kimi --confirm-formal
```

## 数据与评分协议

- 固定 Hugging Face `test` JSONL，revision `cef03a2830944bfb0d201107895ddd0e0e90bf0e`，原始文件 SHA-256 为 `66a2ee8d70208a7a879a17f471ba0ffd097b698265ea4796be99a273fdcc6559`。全量 500 题、2,250 条要求、143 个类别。按 seed 42 在用户型 Easy 和领域型 Hard 之间轮转，并在各类型内轮转类别。本次各取 15 题，覆盖 30 个类别，前 5 条做冒烟。[官方数据集](https://huggingface.co/datasets/kqsong/InFoBench/tree/cef03a2830944bfb0d201107895ddd0e0e90bf0e)
- `question_label` 是要求的类型标签，例如 Content 或 Format。论文中的人工标签针对**某个模型的某份具体回答**。论文描述了专家与众包标注。核对的公开题库和作者 GitHub 文件里未发现可直接下载的逐回答标注，人工审查表的 `human_verdict` 留空供人工填写。[论文](https://arxiv.org/abs/2401.03601) · [作者仓库](https://github.com/qinyiwei/InfoBench)
- `official` 固定作者源码提交 `557fba025e7d570464fe47d7ead8d81019d05992` 的 YES/NO 提示与判定规则。同一答案下每条要求各发一次请求，后续回合携带之前的问答。前缀 YES/NO 优先，然后按官方大小写规则回退。本项目更换 Judge，加入有限重试、截断检测和评分覆盖率，因此成绩属于本项目抽样与模型配置。[官方评测代码](https://github.com/qinyiwei/InfoBench/blob/557fba025e7d570464fe47d7ead8d81019d05992/evaluation.py)
- `atomic` 对每条要求使用独立 JSON 请求，只提供原始指令、输入、候选回答和当前要求。要求 `verdict`、`reason`、`evidence`，非空证据必须是候选原文子串。两种协议的 Judge 缓存、结果目录和成绩各自独立。候选只接收指令和输入，Judge 请求不提供候选模型名。
- DRFR = 通过要求数 ÷ 全部要求数，等同 Requirement-level Pass Rate。Prompt-level Mean Pass 先逐题算比例再平均，All-pass 逐题要求全部通过。另报每个类别、覆盖率和已尝试要求中的 Judge 错误率。只要评分未完备，正式 DRFR 为空，观察到的通过率和覆盖率另列。成功请求但输出为空的候选记为未完成，截断候选按已返回文本评分并标记。InFoBench 不进入 M1 综合 Index。[DRFR 公式](https://arxiv.org/pdf/2401.03601)

## 结果与阅读顺序

`generations.jsonl` 和 `judgments.jsonl` 是逐次持久化的日志。同一个检查键有重试记录时，最终记录包含各次尝试。汇总用量包含复用的记录，命令输出的 `requests_this_command` 单列本次发出的请求。缺失的 API Token 字段保留为缺失，成本按有用量记录的请求估算，同时记录缺失计费信息的次数。

`results.jsonl`、`summary.json`、`badcases.jsonl` 和 `leaderboard.json` 保存聚合结果。正式运行生成最多 20 条有代表性的 `human_review.jsonl`，包含可用的通过、失败、异常和截断样本。官方 YES/NO 协议不返回理由和引用，结构化协议才提供这些信息。

读代码可顺着这条链路走：

1. `datasets/infobench.py` 的 `sample_tasks()` 和 `make_task()` 负责题单。
2. `infobench/__main__.py` 的 `evaluate()` 决定运行阶段。
3. `infobench/pipeline.py` 的 `generation()`、`record()` 和 `judgment()` 管理模型调用、评分顺序和缓存。
4. `infobench/protocol.py` 的 `judge_messages()` 与 `parse_judgment()` 负责评分协议。
5. `infobench/metrics.py` 的 `scores()` 和 `publish()` 负责指标、排行榜与人工复核样本。
