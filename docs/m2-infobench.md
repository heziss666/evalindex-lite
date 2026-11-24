# M2 · InFoBench 与 LLM Judge

离线实现已完成。37 项单元与回归测试通过，包含本地 Mock HTTP 的四种运行模式、错误和重试、断点续跑、评分协议隔离及无 API 重聚合。正式题单和冒烟题单分别从远端及同 SHA-256 的本地原始文件导出，结果逐字节一致。外部模型 API 请求为 0。真实冒烟需要本机配置 API Key。正式实验在冒烟结果核验并获得确认后执行。

## 配置 API Key

在项目根目录运行以下 PowerShell 命令。现有 `.env` 会保留。

```powershell
if (!(Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
code .env
```

在本机 `.env` 给以下三个变量各填一行实际密钥，也可以在运行前由当前终端环境提供。环境变量优先于 `.env`。模型、Base URL、超时、重试、并发和价格在 `configs/infobench.json` 调整，`.env` 已被 Git 忽略。

| 角色 | 模型 ID | Base URL | `.env` 变量 |
| --- | --- | --- | --- |
| Candidate A | `qwen3.7-flash-2026-07-15` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` |
| Candidate B | `glm-4.7-flash` | `https://open.bigmodel.cn/api/paas/v4` | `BIGMODEL_API_KEY` |
| Judge A | `deepseek-v4-pro` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |

Qwen 示例对应百炼北京按量付费，使用同地域 Key，也可以填控制台给出的业务空间专属地址。Base URL 由客户端追加 `/chat/completions`。三个角色均配置关闭思考，候选输出上限 2,048 tokens，Judge 上限 256 tokens，并发默认 2。GLM 免费接口实际可用额度及限流以账号为准。[百炼接口](https://help.aliyun.com/zh/model-studio/base-url) · [智谱模型与接口](https://docs.bigmodel.cn/cn/guide/models/free/glm-4.7-flash) · [智谱免费公告](https://www.zhipuai.cn/zh/news/148) · [DeepSeek 接口](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)

## 费用估算

按 2026-11-24 可查的官方人民币单价，单位为每百万 Token。北京百炼短输入档 Qwen 约 ¥0.20 输入和 ¥0.80 输出。GLM 按免费档 ¥0。DeepSeek Pro 高峰为 ¥9.00 未缓存输入和 ¥27.00 输出，空闲为 ¥4.50 和 ¥13.50。实际账单以控制台为准。 [百炼价格](https://help.aliyun.com/zh/model-studio/model-pricing) · [智谱价格](https://bigmodel.cn/pricing) · [DeepSeek 价格与时段](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

| 阶段 | 题数 | 每个模型的要求数 | 生成 / Judge 请求 | Pro Judge 空闲 / 高峰 | Flash Judge 空闲 / 高峰 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 冒烟 | 5 | 22 | 10 / 44 | ¥0.22 / ¥0.43 | ¥0.05 / ¥0.10 |
| 正式 | 30 | 129 | 60 / 258 | ¥1.25 / ¥2.49 | ¥0.29 / ¥0.57 |

假设每条候选回答 600 输出 tokens、每条 Judge 回复 12 tokens，输入按约 4 字符/token 加消息开销估计。两行是各阶段独立运行的预算，未计重试、缓存或免费券。正式运行复用冒烟成功记录时，首次完整成功后还需约 50 次生成和 214 次 Judge 请求。若候选和 Judge 都用满配置的输出上限，高峰下冒烟与正式约 ¥1.51、¥8.78，依然是场景估计。

建议首轮采用 Pro Judge 并在空闲时段运行。它是该平台的较强档位，用于评分时与两个候选模型分属不同平台。其准确性需要人工复审验证。若优先节省，可以把 `judge_a.model` 改为 `deepseek-flash`，高峰 `pricing` 改为输入 2、缓存输入 0.04、输出 8。换 Judge 后使用新的运行目录，分别查看成绩。[DeepSeek 模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

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
python -m evalindex.infobench end-to-end
```

也可分开执行。默认共用 `runs/m2/smoke/official/`。

```powershell
python -m evalindex.infobench generate
python -m evalindex.infobench judge
python -m evalindex.infobench aggregate
```

用冒烟生成的回答做少量结构化 Judge 验证时，从原运行复用候选回答。

```powershell
python -m evalindex.infobench judge --protocol atomic --resume-from runs/m2/smoke/official
```

确认正式预算后运行下列命令。相同题目、模型配置、回复和评分提示的成功记录会复用。重复执行同一命令可续跑。

```powershell
python -m evalindex.infobench end-to-end --data data/benchmarks/m2/tasks.jsonl --resume-from runs/m2/smoke/official --confirm-formal
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
