# Memory V1: ContextManager 接入运行时 — 设计复盘

## 背景

记忆系统的 V0 状态：读路径完成（memory.render() → SystemPromptBuilder.build() → prompt 注入），写路径完成（工具执行后自动 set_task/touch_file/append_note），评测框架完成（14 任务三组对照实验）。但 ContextManager（预算裁剪引擎）是死代码，记忆注入走全量 render() 无筛选无预算。

V1 目标：让 ContextManager 接管 prompt 构建主入口，记忆改为分层注入。

## 改动

### 5 个 Implementation Units

| Unit | 文件 | 改动 |
|------|------|------|
| U1 | `src/agent/prompts/builder.py` | 新增 `build_prefix()` 静态前缀方法 |
| U2 | `src/agent/context/history_formatter.py` | 新建模块，messages → 结构化摘要 |
| U3 | `src/agent/memory/manager.py` + `renderer.py` | `assemble_layered()` + `select_relevant_file_summaries()` + 分层渲染 |
| U4 | `src/agent/core/loop.py` | `_build_system_prompt()` 改为走 ContextManager 路径 |
| U5 | 实验验证 | 14 任务真实模型对照实验 |

### 关键设计决策

**ContextManager 保持 5-section 签名不变。** memory 层在调用前由 MemoryManager 组装成一个字符串。理由：改动面最小，ContextManager 保持通用性。

**SystemPromptBuilder 降级为静态前缀提供者。** `build_prefix()` 只返回 identity + behavior + tool_guide（~380 tokens），不再拼装 dynamic context。

**history formatter 独立成模块。** 不塞进 loop.py 或 ContextManager。职责单一，可独立测试。

**memory 组装顺序固定：task → recent_files → file_summaries → episodic_notes。** 超出预算时从后往前截断，保证 task 和 recent_files 优先保留。

## 退化与修复

### 第一次实验：memory_on 从 100% 降到 86%

两个任务退化：`fact_manager_methods` 和 `history_loop_config`，都是 0 tool_calls — 模型从记忆"猜"答案，猜错。

### 定位过程

1. 加 ContextMetadata 诊断日志，记录每个 section 的 raw/rendered tokens 和 was_truncated
2. 发现退化任务的 metadata 显示零截断 — 排除"预算不够"的假设
3. 逐行审查 prompt 组装链路，发现两个 bug

### Bug 1：history + current_request 重复注入

`format_history(self._messages)` 包含了最后一条 user 消息（即当前请求），随后又单独提取 `current_request`。当前请求在 prompt 中出现两次，浪费 token 并增加截断概率。

**修复：** history 排除最后一条 user 消息（`self._messages[:last_user_idx]`）。

### Bug 2：file_summaries 的 recent_files 优先规则失效

`touch_file()` 存相对路径（display_path），`update_file_summary()` 存绝对路径（abs_path）。`select_relevant_file_summaries()` 里 `if path in recent` 永远匹配不上。

**修复：** 做 basename + normpath 双重匹配。

### 修复后：memory_on 回到 100%，零截断

| 指标 | 修复后 memory_on | V0 基线 |
|------|----------------|---------|
| correct_rate | **100%** | 100% |
| repeated_reads | 1 | 1 |
| 截断 | 0 sections | N/A |

## 经验总结

1. **不要假设退化原因。** 第一直觉是"预算不够"，但 metadata 证明零截断。先加诊断，再下结论。
2. **路径归一化是跨模块集成的高频坑。** 两个模块各自用不同格式的路径，集成时静默失败。写入和读取必须用同一套路径规范。
3. **prompt 组装链路的"重复注入"很隐蔽。** history 和 current_request 各自看起来都对，但组合在一起就重复了。需要从端到端视角审查 prompt 的每个 section。
4. **14 任务对照实验是有效的回归检测。** 6 个任务时所有配置都是 100%，看不出差异。14 个任务才有足够区分度。
5. **ContextMetadata 是调试 prompt 工程的利器。** 每个 section 的 raw/rendered tokens + was_truncated，能快速定位是哪个 section 出了问题。
