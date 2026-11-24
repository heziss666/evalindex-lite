# 给 Codex 的第一轮开发任务

在现有 EvalIndex Lite 仓库中实现 **真实 MMLU-Pro 小规模评测接入**，不要同时扩展其他 Benchmark。

## 要求

1. 读取 `README.md` 与当前源代码，先运行现有单测及 Replay，保留现有接口。
2. 新增 `datasets/mmlu_pro.py`：用 `datasets` 库加载 `TIGER-Lab/MMLU-Pro`，从 `test` split 可复现地抽取 30 道题；记录完整 dataset revision / subset seed / 题目 id、题目与选项、正确答案。
3. 用明确的 Prompt 模板输入题目及选项，指定模型最后只用 `Final Answer: X` 作答。不要让模型看到 `answer` 字段。默认 Zero-shot，参数写入配置。
4. 与项目现有 `--model` API 适配器对接；新脚本从官方题库构造 JSONL，并调用现有 CLI 运行。若实际分割名/字段与描述不同，以公开数据集实际 schema 为准，不猜测。
5. 新增 `analysis/badcase.py`：输出题目 id、正确答案、模型输出、解析结果、错误类型；解析失败另行统计。
6. 至少写 8 个测试覆盖：正确选项、错误选项、格式失败、输出里多个字母、选项字母大小写、重复 id、只提供题目不泄露答案、空模型输出。
7. 保存可复现信息：模型 ID、Prompt 模板版本、采样参数、HF 数据集版本或 revision、commit hash；不要在仓库写死 API Key。
8. 首先用 Replay 验证，再用 5 道真实题对服务端 smoke test。确认成功后再跑 30 道。

## 完成标准

- `python -m unittest discover -s tests -v` 全部通过。
- 新增 `README.md` 的“运行 MMLU-Pro”章节含准确可运行的命令。
- 生成一份 `results.jsonl` 和 `summary.json`，并分析至少 3 条 Badcase。
- 不改变 Gold 以适配模型答案；不把非官方简化评分包装为官方排名成绩。
- 每完成一个独立步骤检查输出和异常，不做未经检验的大规模改造。
