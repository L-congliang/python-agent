# 记忆系统 — 面试表述参考

## 一句话定位

构建了一个类 Claude Code 的 CLI Agent，记忆系统实现了从"全量注入"到"预算裁剪 + 分层注入 + 真实对照评测"的完整工程闭环。

## 项目背景（30 秒讲清楚）

做了一个开源 AI 编程助手（Python），模仿 Claude Code 的架构。核心挑战之一是：Agent 的上下文窗口有限，记忆系统需要在"记住足够多"和"不超预算"之间找到平衡。

## 我做了什么（2 分钟）

### 1. 记忆写路径闭环

Agent 每次执行工具后，自动写入记忆：
- `read` 工具 → 记录文件访问 + 更新文件摘要
- `write/edit` 工具 → 记录文件访问
- `bash/grep` 工具 → 记录执行结果到 episodic notes
- 用户输入 → 更新 task summary

**面试能讲的点：** 为什么用 hook 模式（在工具执行后自动写入）而不是让用户手动管理记忆？因为 Agent 的记忆应该是"无感"的 — 用户不需要知道记忆系统的存在。

### 2. 记忆分层注入

不是把所有记忆一股脑塞进 prompt，而是分层组装：
- **task**（总是注入）— 当前任务描述
- **recent_files**（总是注入最近 3-5 个）— 最近访问的文件
- **file_summaries**（按相关性取 top-k）— 文件内容摘要
- **episodic_notes**（检索命中后注入 1-3 条）— 关键事件笔记

每层有独立的 token 预算，超出时从后往前截断（episodic_notes 先丢，task 最后丢）。

**面试能讲的点：** 为什么不全量注入？因为实验数据显示，无关记忆会导致 repeated_reads 上升（2 vs 1）— 噪声记忆反而让 Agent 变差。

### 3. ContextManager 预算裁剪

把 prompt 组装从"字符串拼接"升级为"预算裁剪"：
- 5 个 section：prefix（3600）、tools（2000）、memory（1600）、history（5200）、current_request（不限）
- 总预算 12,000 tokens
- 超出时按优先级裁剪：history 先裁，memory 次之，tools 再次之，prefix 和 current_request 不裁

**面试能讲的点：** 为什么 prefix 和 current_request 不裁？因为实验（P6 prompt ablation）证明，identity section 从 13.6% 提升到 59.1% 的 tool_accuracy — 静态前缀是 Agent 正确选择工具的关键。

### 4. 真实对照评测

建立了 memory_on / memory_off / memory_irrelevant 三组对照实验：
- 14 个任务，覆盖 7 类场景
- 用真实模型（mimo v2.5pro）跑，不是 mock
- 指标来自运行时数据（tool_history + verifier），不是硬编码

**实验结果：**
- memory_on 正确率 100% vs memory_off 86% — 记忆系统对正确率有显著提升
- memory_irrelevant repeated_reads=2 vs memory_on=1 — 噪声记忆导致额外重复读取

**面试能讲的点：** 为什么不用 FakeModelClient？因为 mock 模型的所有配置都是 100%，看不出差异。真实模型才能暴露记忆系统的实际效果。

## 遇到的问题（1 分钟）

### 退化 100% → 86%

接入 ContextManager 后，memory_on 正确率从 100% 降到 86%。第一直觉是"预算不够"，但加了 ContextMetadata 诊断后发现零截断。

**真正原因：**
1. history 和 current_request 重复注入（当前请求在 prompt 中出现两次）
2. file_summaries 的路径匹配失败（相对路径 vs 绝对路径不一致）

**修复后回到 100%。**

**面试能讲的点：** 这个过程体现了"先诊断再修复"的工程方法论 — 不要假设退化原因，先加诊断数据，再下结论。

## 技术栈

Python 3.12+, Anthropic SDK, mimo v2.5pro 模型, rich + prompt_toolkit, pytest

## 量化成果

| 指标 | 数值 |
|------|------|
| 记忆系统正确率提升 | 100% vs 86%（memory_on vs memory_off） |
| 评测任务数 | 14 个，覆盖 7 类场景 |
| 测试覆盖 | 816 tests passed |
| 代码量 | ~2000 行（记忆系统 + 评测框架） |
