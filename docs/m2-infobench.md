# M2 · InFoBench 与 LLM Judge

当前 Candidate B 暂用 Kimi K3.1 Pro，已完成与 Qwen 的 5 题真实冒烟。30 题正式结果仍为前一轮 Qwen / GLM 的记录。

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

Kimi K3.1 Pro 普速版每百万 Token 未命中输入 ¥13、缓存命中输入 ¥1.30、输出 ¥68。按每题平均 1,200 输出 tokens 估算，Kimi 生成部分约 ¥0.41 / 5 题、¥2.48 / 30 题，另计新增的 Judge 调用、重试和缓存写入费。用 `dry-run` 查看当前设置的整轮预算。[Kimi 官方单价](https://www.kimi.com/news/kimi-k3-1-pro) · [缓存计费](https://platform.kimi.com/docs/pricing/chat)

下表保留 GLM 方案的预算基线。按 2026-11-24 可查的官方人民币每百万 Token 单价，北京百炼短输入档 Qwen 约 ¥0.20 输入和 ¥0.80 输出。GLM 按免费档 ¥0。DeepSeek Pro 高峰为 ¥9.00 未缓存输入和 ¥27.00 输出，空闲为 ¥4.50 和 ¥13.50。实际账单以控制台为准。[百炼价格](https://help.aliyun.com/zh/model-studio/model-pricing) · [智谱价格](https://bigmodel.cn/pricing) · [DeepSeek 价格与时段](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

| 阶段 | 题数 | 每个模型的要求数 | 生成 / Judge 请求 | Pro Judge 空闲 / 高峰 | Flash Judge 空闲 / 高峰 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 冒烟 | 5 | 22 | 10 / 44 | ¥0.22 / ¥0.43 | ¥0.05 / ¥0.10 |
| 正式 | 30 | 129 | 60 / 258 | ¥1.25 / ¥2.49 | ¥0.29 / ¥0.57 |

假设每条候选回答 600 输出 tokens、每条 Judge 回复 12 tokens，输入按约 4 字符/token 加消息开销估计。两行是各阶段独立运行的预算，未计重试、缓存或免费券。正式运行复用冒烟成功记录时，首次完整成功后还需约 50 次生成和 214 次 Judge 请求。若候选和 Judge 都用满配置的输出上限，高峰下冒烟与正式约 ¥1.51、¥8.78，依然是场景估计。

建议首轮采用 Pro Judge 并在空闲时段运行。它是该平台的较强档位，用于评分时与两个候选模型分属不同平台。其准确性需要人工复审验证。若优先节省，可以把 `judge_a.model` 改为 `deepseek-flash`，高峰 `pricing` 改为输入 2、缓存输入 0.04、输出 8。换 Judge 后使用新的运行目录，分别查看成绩。[DeepSeek 模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

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

### 前一轮 GLM 冒烟

2026-11-24 晚间（北京时间）使用 `official` 协议、固定 5 题和 DeepSeek V4 Pro 完成真实冒烟。每个模型有 22 条要求，两边评分覆盖率都是 100%。

| 候选模型 | DRFR | Prompt-level Mean Pass | Prompt-level All-pass |
| --- | ---: | ---: | ---: |
| Qwen3.7 Flash | 86.36%（19/22） | 85.0% | 60.0%（3/5） |
| GLM-4.7-Flash | 68.18%（15/22） | 66.5% | 20.0%（1/5） |

| 角色 | API 请求 | 已报告输入 tokens | 已报告输出 tokens |
| --- | ---: | ---: | ---: |
| Qwen | 5 | 385 | 2,979 |
| GLM | 20 | 344 | 2,753 |
| DeepSeek Judge | 44 | 37,419 | 44 |
| 合计 | 69 | 38,148 | 5,776 |

GLM 的 20 次请求中有 15 次返回 HTTP 429，未上报用量。首次使用并发 2，切到并发 1 后续跑两次，最终 5 题均生成成功，最慢一次成功请求约 72 秒。续跑期间复用了已完成的回答与 Judge 判定。44 条 Judge 回复均成功解析，候选与 Judge 成功输出均未截断。

DeepSeek 输入中 26,112 tokens 命中缓存，11,307 tokens 未命中。按已上报用量和空闲时段单价估算，总费用约 **¥0.058**。结算金额以平台账单为准。离线 Aggregate 的 API 调用数为 0，重新生成的五个结果文件均与原文件一致。逐次生成与判分记录已随续跑保存在 `runs/m2/tasks/official/`，旧冒烟目录已清理。[DeepSeek 缓存与时段单价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

## 30 题正式评测

经确认后，于 2026-11-24 20:05–20:17（北京时间）运行正式题单。每个候选有 30 题、129 条要求，复用冒烟的 10 次成功生成和 44 次 Judge 判定。题单 SHA-256 为 `b567c1a0b09e0dd4131e12d64d73717ea9fe2fdcfa6258db40e13dfc8a4e2c19`。

| 候选模型 | 生成覆盖 | 评分覆盖 | DRFR | Prompt Mean Pass | Prompt All-pass |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3.7 Flash | 30/30 | 100.00%（129/129） | 82.17%（106/129） | 81.36% | 56.67%（17/30） |
| GLM-4.7-Flash | 5/30 | 17.05%（22/129） | 待补齐 | 待补齐 | 待补齐 |

Qwen 的 3 份回答达到输出上限，并按已返回文本评分。DeepSeek 完成两边可评分的全部 151 条要求，Judge 错误为 0。GLM 的 25 个新增题未生成，复用的 5 题单独观察为 15/22 条通过。由于覆盖率不同，当前榜单只列完成评分的候选，双模型比较需等 GLM 补齐。

正式阶段新增 **213 次请求**，包括 25 次 Qwen 生成、81 次 GLM 尝试和 107 次 Judge 调用。其中 GLM 新增 79 次 HTTP 429、2 次超时，这些失败未上报用量。单并发和两轮延时探测均未恢复。探测记录到官方业务错误码 `1305`（访问量过大）与 `1302`（账户速率限制）。客户端现在保留数字错误码并延长 GLM 429 的退避；明确的账户或配额错误会结束该次重试。[智谱官方错误码](https://docs.bigmodel.cn/cn/api/api-code)

新增已报告用量为 **121,116 输入 tokens、19,805 输出 tokens**。按实际缓存量和空闲时段单价估算，新增费用约 **¥0.179**，冒烟加正式累计约 **¥0.237**。这些是按已上报用量估算的金额，结算以平台账单为准。[DeepSeek 时段及缓存单价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

本地 `runs/m2/tasks/official/` 保存结果、错误记录和 `human_review.jsonl`。复核清单包含 20 条判定，覆盖两个候选的通过与失败，也包含关联截断回答的记录。人工标签留空。离线 Aggregate 发出 0 次请求，重聚合的五个结果文件与保存版本逐字节一致。

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
python -m evalindex.infobench end-to-end --resume-from runs/m2/tasks/official
```

上一轮正式目录存在时，以上命令会复用冒烟题对应的 Qwen 回答和判分，Kimi 的结果写入 `runs/m2/smoke/official-kimi/`。也可分开执行。

```powershell
python -m evalindex.infobench generate --resume-from runs/m2/tasks/official
python -m evalindex.infobench judge --resume-from runs/m2/tasks/official
python -m evalindex.infobench aggregate
```

用冒烟生成的回答做少量结构化 Judge 验证时，从原运行复用候选回答。

```powershell
python -m evalindex.infobench judge --protocol atomic --resume-from runs/m2/smoke/official-kimi
```

确认正式预算后运行下列命令。相同题目、模型配置、回复和评分提示的成功记录会复用。重复执行同一命令可续跑。

```powershell
python -m evalindex.infobench end-to-end --data data/benchmarks/m2/tasks.jsonl --resume-from runs/m2/smoke/official-kimi --resume-from runs/m2/tasks/official --confirm-formal
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
