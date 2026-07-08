# Task 2.2 分析报告：ScriptedModelClient + 真实 AgentLoop 对现有任务的表现

## 实验设置

- 用 ScriptedModelClient 驱动真实 AgentLoop（替代 `_run_mock_task()`）
- 默认脚本：读取第一个 target_file，然后用 expected_substrings 作为最终回复
- setup_turns 用独立 FakeModelClient（不消耗主任务 script rounds）
- 对比 memory_on vs memory_off

## 结果

| 指标 | memory_on | memory_off | 差异 |
|------|-----------|------------|------|
| correct_rate | 58.33% (14/24) | 58.33% (14/24) | 0 |
| avg_tool_calls | 1.00 | 1.00 | 0 |
| avg_repeated_reads | 0.00 | 0.00 | 0 |
| memory_hit_rate | 0.00% | 0.00% | 0 |

## 关键发现

### 1. memory_on 和 memory_off 完全无差异

原因：ScriptedModelClient 的默认脚本不区分 memory 状态。无论 memory 是否启用，脚本都执行相同的 tool call 序列。这证实了设计文档的核心判断：

> "FakeModelClient 的行为可能太'完美'，无法体现 memory 带来的效率差异"

### 2. 正确率与任务类型强相关

通过的任务（14/24）都是 target_file 在 fixture 目录中存在、且 expected_substrings 在文件内容中的任务：
- `edit_config_update`（config.json ✓）
- `recall_api_key`（api_config.py ✓）
- `dep_use_api_key`（api2.py ✓）
- `multi_add_timeout`（service.py ✓）
- 等

失败的任务（10/24）分两类：
- **fixture 不存在**：`history_loop_config`（target=`src/agent/core/loop.py`，不在 fixture 目录）
- **expected_substrings 不在文件中**：`dep_update_header`（api2.py 存在但内容不匹配）

### 3. memory_hit_rate = 0% 的含义

所有有 setup_turns 的任务都 reread 了 target_file（mem_hit=0）。这是脚本行为决定的——脚本总是读第一个 target_file，不管 memory 是否可用。

### 4. 对后续任务设计的启示

要让 memory_on 和 memory_off 产生差异，需要：
- **脚本需要区分 memory 状态**：memory_on 时跳过 reread，memory_off 时执行 reread
- **或者设计 cross-session 任务**：信息在另一个 session 文件中，memory_off 无法获取

## 结论

当前默认脚本证明了基础设施能工作（真实 tool 执行、真实指标测量），但不产生 memory 敏感的差异。Task 2.3 需要设计专门的 memory-sensitive 脚本或任务。
