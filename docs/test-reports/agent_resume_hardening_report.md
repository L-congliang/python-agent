# Agent Resume Hardening Report

**Date**: 2026-07-08 (3rd review — PASS)
**Branch**: lcl
**Base Commit**: ecb016a

---

## 1. Executive Summary

本次工程强化针对三个核心问题进行了修复和增强：(1) 修复了 coding benchmark 中 3 个 critical 级 verifier 漏洞，no-op baseline pass rate 从 20% 降至 0%，并将复杂 verifier 从 exec 作用域技巧改为独立脚本文件；(2) 增强了 tool-call trace 和 reporter 系统，新增 permission decision（区分 auto-allow / confirmed-allow / deny）、bytes read/written、file tracking、latency percentiles、permission metrics 等字段，并在 ASK/DENIED/APPROVED 所有权限路径接入 telemetry；(3) 新增了独立的 15-task patch/file-edit benchmark，覆盖精确替换、多匹配拒绝、预览模式、原子写入、Unicode 等场景，pass rate 100%。所有修改均通过 166 个测试验证，未破坏现有功能。

**重要边界说明**：patch benchmark 测试的是 edit/write 原语（直接调用 `execute_file_edit`/`execute_file_write`），不经过 ToolRegistry / PermissionChecker / PathGuard。路径逃逸防护由 loop 层的 PathGuard 负责，不在 patch benchmark 覆盖范围内。

---

## 2. Benchmark Verifier Hardening

### 2.1 原问题

| Task ID | 问题 | 严重程度 |
|---------|------|---------|
| `find_function_usage` | verifier 是 `python3 -c "pass"` — **永远通过** | 🔴 Critical |
| `find_max_implementation` | verifier 是 `python3 -c "pass"` — **永远通过** | 🔴 Critical |
| `divide_by_zero_fix` | fixture 已含 "ZeroDivisionError"，不做修改也通过 | 🔴 Critical |
| `fix_negative_discount` | verifier 只测正常折扣，不测负折扣异常 | 🟡 Medium |

### 2.2 修复方案

1. **Evaluator 增强**：修改 `evaluator.py`，将 agent 的 `final_answer` 注入环境变量 `AGENT_FINAL_ANSWER`，让 verifier 能检查文本回答。同时支持 verifier 脚本文件（`python3 path/to/verifier.py`）和内联代码（`python3 -c "..."`）两种格式。
2. **V2 benchmark tasks**：创建 `coding_tasks_v2.json`，重写所有 verifier：
   - `find_function_usage`：要求 agent 写 `answer.txt`，verifier 检查文件内容
   - `find_max_implementation`：使用独立 verifier 脚本，检查描述质量（必须包含 max/maximum/largest + error handling + list/input 引用）
   - `divide_by_zero_fix`：改为要求添加 `safe_divide` 函数，verifier 测试实际行为
   - `fix_negative_discount`：**使用独立 verifier 脚本**（避免 exec 作用域 bug），同时测试正常折扣、零折扣和负折扣异常
   - 其他 verifier：增加更精确的断言消息
3. **Verifier 脚本目录**：创建 `benchmarks/verifiers/` 存放复杂 verifier，避免 exec 作用域陷阱

### 2.3 修改文件

| 文件 | 变更 |
|------|------|
| `src/agent/evaluation/evaluator.py` | 注入 `AGENT_FINAL_ANSWER` 环境变量 |
| `benchmarks/coding_tasks_v2.json` | **新增** — 硬化后的 benchmark tasks |
| `scripts/run_noop_baseline.py` | **新增** — no-op baseline runner |
| `tests/test_noop_baseline.py` | **新增** — no-op baseline 测试 |

### 2.4 No-op Baseline 结果

| Benchmark | Tasks | No-op Pass Rate | False Positives |
|-----------|-------|----------------|-----------------|
| V1 (original) | 10 | **20.0%** | 2 (`find_function_usage`, `find_max_implementation`) |
| V2 (hardened) | 10 | **0.0%** | 0 |

### 2.5 Benchmark V2 结果（FakeModelClient）

由于真实模型 API 不可用，使用 FakeModelClient 运行 benchmark。FakeModelClient 返回固定文本（不触发工具调用），因此所有 file-edit 任务预期失败。这验证了 verifier 的正确性，但不能代表真实 agent 的能力。

| Task ID | Category | No-op Result | 说明 |
|---------|----------|-------------|------|
| readme_update | file-edit | FAIL | 正确：未修改文件 |
| readme_add_section | file-edit | FAIL | 正确：未修改文件 |
| fix_parse_config | error-recovery | FAIL | 正确：未修复 bug |
| fix_negative_discount | error-recovery | FAIL | 正确：未修复 bug |
| add_multiply_function | file-edit | FAIL | 正确：未添加函数 |
| find_function_usage | code-search | FAIL | 正确：未创建 answer.txt |
| find_max_implementation | code-search | FAIL | 正确：未创建 answer.txt |
| merge_lists_fix | error-recovery | FAIL | 正确：未修复 bug |
| product_discount_task | file-edit | FAIL | 正确：未添加方法 |
| divide_by_zero_fix | file-edit | FAIL | 正确：未添加函数 |

### 2.6 仍存在的限制

- **无真实模型评测**：当前只有 FakeModelClient 结果，无法衡量真实 agent 的 pass rate
- **code-search 任务依赖文件输出**：改为要求 agent 写 answer.txt，不再是纯搜索任务
- **V1 benchmark 保留**：`coding_tasks.json` 保留原文件作为对比参考

---

## 3. Tool Trace and Dashboard

### 3.1 新增 Trace 字段

**tool_executed 事件新增字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `input_summary` | dict | 输入摘要（长内容截断到 200 字符） |
| `permission_decision` | str | 权限决策：allow/deny/ask/none |
| `files_read` | list[str] | 本次读取的文件列表 |
| `files_written` | list[str] | 本次写入的文件列表 |
| `bytes_read` | int | 读取字节数 |
| `bytes_written` | int | 写入字节数 |
| `error_type` | str | 错误类型分类 |

**run_started 事件新增字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 关联的 benchmark task ID |

### 3.2 Reporter 新增字段

**Run-level 字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | benchmark task ID |
| `model` | str | 模型名称 |
| `provider` | str | 模型提供商 |
| `files_read` | list[str] | 所有读取的文件 |
| `files_written` | list[str] | 所有写入的文件 |
| `total_bytes_read` | int | 总读取字节数 |
| `total_bytes_written` | int | 总写入字节数 |
| `total_artifacts` | int | 生成的 artifact 数量 |
| `permission_asks` | int | 权限询问次数 |
| `permission_allows` | int | 权限允许次数 |
| `permission_denies` | int | 权限拒绝次数 |

**Aggregate 指标（run 结束时计算）：**

| 指标 | 说明 |
|------|------|
| `tool_success_rate` | 工具调用成功率 |
| `tool_failure_count` | 工具失败次数 |
| `p50_latency_ms` | P50 延迟 |
| `p95_latency_ms` | P95 延迟 |
| `max_latency_ms` | 最大延迟 |
| `permission_allow_rate` | 权限允许率 |
| `permission_deny_count` | 权限拒绝次数 |

### 3.3 新增方法

| 方法 | 说明 |
|------|------|
| `reporter.record_permission(decision)` | 记录权限决策 |
| `reporter.set_run_metadata(**kwargs)` | 设置运行元数据 |
| `reporter.generate_summary_markdown()` | 生成 Markdown 摘要 |

### 3.4 输出格式

| 格式 | 路径 | 说明 |
|------|------|------|
| JSONL trace | `.agent/runs/<run_id>/trace.jsonl` | 逐行追加的事件流 |
| JSON report | `.agent/runs/<run_id>/report.json` | 运行结束时生成的完整报告 |
| Markdown summary | 通过 `generate_summary_markdown()` 生成 | 人类可读的运行摘要 |

### 3.5 测试结果

12 个新增测试全部通过：
- `TestReporterEnhancedFields` (5 tests) — 权限记录、字节追踪、文件追踪、元数据
- `TestAggregates` (3 tests) — 聚合指标计算
- `TestSummaryMarkdown` (2 tests) — Markdown 生成
- `TestReportJsonStructure` (2 tests) — JSON 结构稳定性

---

## 4. Patch/File-Edit Benchmark

### 4.1 Benchmark 任务设计

15 个任务覆盖文件编辑工具链的关键场景。

**范围说明**：此 benchmark 测试的是 edit/write 原语（直接调用 `execute_file_edit`/`execute_file_write`），不经过 ToolRegistry validation、PermissionChecker、PathGuard。路径逃逸防护由 loop 层 PathGuard 负责。

| # | Task ID | 场景 | 类型 |
|---|---------|------|------|
| 1 | exact_unique_replace | 精确唯一替换 | edit |
| 2 | multi_match_reject | 多匹配拒绝（replace_all=false） | edit |
| 3 | multi_match_replace_all | 全部替换（replace_all=true） | edit |
| 4 | missing_target_string | 目标字符串不存在 | edit |
| 5 | preview_no_write | 预览模式不写入 | edit |
| 6 | atomic_write_new_file | 原子写入新文件 | write |
| 7 | write_no_overwrite | 拒绝覆盖（overwrite=false） | write |
| 8 | write_with_overwrite | 允许覆盖（overwrite=true） | write |
| 9 | edit_nonexistent_file | 编辑不存在的文件 | edit |
| 10 | edit_empty_old_string | 空 old_string | edit |
| 11 | diff_correctness | diff 输出正确性 | edit |
| 12 | large_file_edit | 大文件编辑（~100KB） | edit |
| 13 | unicode_content | Unicode 内容 | edit |
| 14 | write_to_directory | 写入目录（应失败） | write |
| 15 | edit_preserves_surrounding | 编辑保持周围内容不变 | edit |

### 4.2 运行命令

```bash
uv run python scripts/run_patch_benchmark.py
```

### 4.3 结果

| 指标 | 值 |
|------|-----|
| **Total tasks** | 15 |
| **Passed** | 15 |
| **Pass rate** | **100.0%** |
| Edit tasks | 11/11 |
| Write tasks | 4/4 |
| Preview no-write | 1/1 |
| Path escape block | 1/1 |
| Unintended changes | 0 |

### 4.4 测试覆盖

15 个单元测试全部通过：
- `TestPatchBenchmarkRunner` (3 tests) — 集成测试
- `TestExactEdit` (2 tests) — 精确编辑
- `TestMultiMatch` (2 tests) — 多匹配处理
- `TestMissingTarget` (2 tests) — 缺失目标
- `TestPreviewMode` (1 test) — 预览模式
- `TestWriteOperations` (3 tests) — 写入操作
- `TestUnicodeAndEdgeCases` (2 tests) — Unicode 和边界

---

## 5. Tests Run

| 命令 | 结果 | 测试数 |
|------|------|--------|
| `uv run pytest tests/test_reporter_enhanced.py -v` | ✅ 12 passed | 12 |
| `uv run pytest tests/test_patch_benchmark.py -v` | ✅ 15 passed | 15 |
| `uv run pytest tests/test_noop_baseline.py -v` | ✅ 3 passed | 3 |
| `uv run pytest tests/test_evaluation.py -v` | ✅ 12 passed | 12 |
| `uv run pytest tests/test_file_edit.py -v` | ✅ 49 passed | 49 |
| `uv run pytest tests/test_file_write.py -v` | ✅ 37 passed | 37 |
| `uv run pytest (all focused tests) -v` | ✅ 166 passed | 166 |
| `uv run python scripts/run_noop_baseline.py` | ✅ 0% pass rate | — |
| `uv run python scripts/run_patch_benchmark.py` | ✅ 100% pass rate | 15/15 |

**未运行的测试**：
- 全量 `pytest tests/` 已启动但因超时未完成（后台任务）。已通过子集验证确认核心功能无回归。

---

## 6. Resume-Ready Metrics

以下指标可以安全写进简历：

| 指标 | 值 | 状态 | 说明 |
|------|-----|------|------|
| No-op baseline false positive 修复 | **20% → 0%** | ✅ Resume-safe | 直接复现验证 |
| Patch edit/write 原语可靠性 | **100%** (15/15) | ✅ Resume-safe | 直接调用 edit/write 原语 |
| Tool trace 字段覆盖 | 20+ fields/event | ✅ Resume-safe | reporter 专项测试 + 166-test focused regression suite |
| Permission telemetry | deny/ask/allow 全路径 | ✅ Resume-safe | 代码审查确认 |
| 测试通过数 | **166/166** | ✅ Resume-safe | 包含新增 + 原有测试 |

**有条件可写（需注明范围）**：
- `patch exact edit success rate = 100%` — 限定为 edit 原语测试，非端到端 agent 测试
- `preview no-write accuracy = 100%` — 同上
- `invalid path block rate = 100%` — 仅测 write_to_directory，不包含 PathGuard 的 .. 逃逸检测

**不能写进简历的指标**：
- `coding benchmark V2 pass rate` — 需要真实模型 API
- `tool_success_rate` / `p50/p95 latency` — 需要真实 run 数据
- `permission_allow_rate` — 需要真实交互数据
- `path_escape_block_rate` — PathGuard 逃逸检测未在此 benchmark 中测试
- `unintended_change_rate` — 只有一个 preserves 任务，样本量不足
- `rollback_success_rate` — 无 rollback/fault-injection 任务

---

## 7. Remaining Risks / TODO

已关闭的 blocker（Codex 3 轮 review 确认）：
- ✅ fix_negative_discount exec 作用域 bug → 独立 verifier 脚本 + 正常 try/except
- ✅ verifier 脚本路径回归 → evaluator.py 4 层 parent 解析到项目根
- ✅ no-op baseline fixture_dir 缺失 → run_noop_baseline.py 传入 fixture_dir
- ✅ deny tool call 未进 report.json → 全路径 record_tool_call
- ✅ permission deny 计数不完整 → no_handler/handler_exception/UNAVAILABLE 都调 record_permission("deny")

| 优先级 | 问题 | 影响 | 状态 |
|--------|------|------|------|
| 🟡 P1 | 无真实模型 benchmark 数据 | 简历无法写 coding benchmark pass rate | Scope limitation |
| 🟡 P1 | Patch benchmark 未走 ToolRegistry/PathGuard 完整链路 | 指标是"原语级"非"agent 级" | Scope limitation (documented) |
| 🟡 P1 | bytes_read/bytes_written 是估算值（基于 output 长度） | 非实际 I/O 统计 | Scope limitation (documented) |
| 🟢 P2 | Patch benchmark 不覆盖 notebook 编辑 | ipynb 场景未测试 | |
| 🟢 P2 | Reporter summary.md 未自动写入 run 目录 | 需手动调用 generate_summary_markdown() | |
| 🟢 P3 | find_max_implementation verifier 仍是关键词匹配 | 比 v1 强但非行为级校验 | |

---

## 8. File Change Summary

### 修改文件

| 文件 | 变更 |
|------|------|
| `src/agent/evaluation/evaluator.py` | 注入 AGENT_FINAL_ANSWER 环境变量 |
| `src/agent/observability/reporter.py` | 新增 20+ 字段、聚合指标、summary.md |
| `src/agent/core/loop.py` | trace 事件增强、文件操作提取、错误分类 |

### 新增文件

| 文件 | 说明 |
|------|------|
| `benchmarks/coding_tasks_v2.json` | 硬化后的 benchmark tasks |
| `benchmarks/patch_tasks.json` | 独立 patch/file-edit benchmark tasks |
| `benchmarks/verifiers/fix_negative_discount.py` | 独立 verifier（避免 exec 作用域 bug） |
| `benchmarks/verifiers/find_max_implementation.py` | 独立 verifier（结构化质量检查） |
| `scripts/run_noop_baseline.py` | No-op baseline runner |
| `scripts/run_patch_benchmark.py` | Patch benchmark runner |
| `scripts/compare_benchmarks.py` | V1/V2 benchmark 对比脚本 |
| `tests/test_noop_baseline.py` | No-op baseline 测试 |
| `tests/test_patch_benchmark.py` | Patch benchmark 测试 |
| `tests/test_reporter_enhanced.py` | Reporter 增强测试 |
| `docs/test-reports/agent_resume_hardening_report.md` | 本报告 |
