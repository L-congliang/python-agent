## Phase 3.2F Follow-up: 更敏感的 Reflection-Sensitive Task 集

### 目标

当前 3 个 memory_sensitive 任务太简单，只能测到"retry 机制有效"，测不到"reflection 内容选对了策略"。本轮新增 5 个混合最优策略的任务，让 prompt-sensitive retry 有机会拉开与 fixed scripted retry 的差距。

### 核心设计

**两个维度分离：**

| 字段 | 职责 | 作用域 |
|------|------|--------|
| `initial_attempt_mode` | 控制 first attempt 是 memory_first 还是 reread_first | 只在 `_build_default_script()` |
| `retry_strategy` | 控制 reflection 后的 retry 路由 | 只在 `ReflectionBuilder` + `PromptAwareClient` |

**不泄漏：** `initial_attempt_mode` 不进入 retry 路径。retry 只认 `ReflectionPlan.retry_strategy`。

**新字段：**
- `initial_attempt_mode: str | None` — "memory_first" | "reread_first" | None（默认按 config）
- `optimal_retry_branch: str | None` — 该任务的最优 retry branch（用于 benchmark 验证）

### 任务分类

| 任务 | Type | initial_attempt_mode | Optimal | 为什么 fixed 会吃亏 |
|------|------|---------------------|---------|-------------------|
| stale_api_url | wrong_memory | memory_first | reread_then_answer | fixed use_memory → 答错 |
| stale_cache_port | wrong_memory | memory_first | reread_then_answer | fixed use_memory → 答错 |
| suff_db_host | wasted_reread | reread_first | use_memory_answer | fixed reread → 浪费 tool call |
| suff_api_key | wasted_reread | reread_first | use_memory_answer | fixed reread → 浪费 tool call |
| partial_config | wrong_memory | memory_first | reread_then_answer | fixed use_memory → 遗漏字段 |

**预期效果：**
- fixed "use_memory": stale/partial 任务 ✗, suff 任务 ✓
- fixed "reread": stale/partial 任务 ✓, suff 任务 ✓(wasted tool)
- prompt-sensitive: stale/partial 选 reread ✓, suff 选 memory ✓(no waste)

### Fixture 文件

新建 `tests/fixtures/memory_experiment/reflection_sensitive_v2/`：

```
api_stale.py:
  API_URL = "https://v2.updated.internal"  # 与 setup 给的旧值不同

cache_stale.py:
  CACHE_PORT = 6380  # 与 setup 给的旧值 6379 不同

database_stable.py:
  DB_HOST = "db.prod.internal"  # 与 setup 给的值相同

api_config_stable.py:
  API_KEY = "sk-prod-abc123xyz789"  # 与 setup 给的值相同

config_partial.py:
  API_KEY = "sk-test-key"
  RATE_LIMIT = 100
  TIMEOUT = 30
  # setup 只提 API_KEY，main 需要 API_KEY + RATE_LIMIT
```

### 5 个新任务定义

```python
# stale_memory: setup 给旧值，main 问真实值
MemoryTask(
    task_id="v2_stale_api_url",
    category="reflection_sensitive_v2",
    dependency_level="L3",
    prompt="What is the API_URL in api_stale.py? Answer with just the URL.",
    setup_turns=["Read api_stale.py. The API_URL is https://v1.old.internal."],
    fixture_dir="reflection_sensitive_v2",
    target_files=["api_stale.py"],
    verifier="contains_text",
    expected_substrings=["https://v2.updated.internal"],
    initial_attempt_mode="memory_first",
    optimal_retry_branch="reread_then_answer",
    retry_branches={
        "use_memory_answer": [[{"type": "text", "text": "https://v1.old.internal"}]],
        "reread_then_answer": [
            [{"type": "tool_use", "id": "c1", "name": "read", "input": {"file_path": "api_stale.py"}}],
            [{"type": "text", "text": "https://v2.updated.internal"}],
        ],
    },
    default_retry_branch="reread_then_answer",
),

MemoryTask(
    task_id="v2_stale_cache_port",
    category="reflection_sensitive_v2",
    dependency_level="L3",
    prompt="What is CACHE_PORT in cache_stale.py? Answer with just the number.",
    setup_turns=["Read cache_stale.py. The CACHE_PORT is 6379."],
    fixture_dir="reflection_sensitive_v2",
    target_files=["cache_stale.py"],
    verifier="contains_text",
    expected_substrings=["6380"],
    initial_attempt_mode="memory_first",
    optimal_retry_branch="reread_then_answer",
    retry_branches={
        "use_memory_answer": [[{"type": "text", "text": "6379"}]],
        "reread_then_answer": [
            [{"type": "tool_use", "id": "c1", "name": "read", "input": {"file_path": "cache_stale.py"}}],
            [{"type": "text", "text": "6380"}],
        ],
    },
    default_retry_branch="reread_then_answer",
),

# memory_sufficient: setup 给正确值，reread 是浪费
MemoryTask(
    task_id="v2_suff_db_host",
    category="reflection_sensitive_v2",
    dependency_level="L3",
    prompt="What is DB_HOST in database_stable.py? Answer with just the hostname.",
    setup_turns=["Read database_stable.py. The DB_HOST is db.prod.internal."],
    fixture_dir="reflection_sensitive_v2",
    target_files=["database_stable.py"],
    verifier="contains_text",
    expected_substrings=["db.prod.internal"],
    initial_attempt_mode="reread_first",
    optimal_retry_branch="use_memory_answer",
    retry_branches={
        "use_memory_answer": [[{"type": "text", "text": "db.prod.internal"}]],
        "reread_then_answer": [
            [{"type": "tool_use", "id": "c1", "name": "read", "input": {"file_path": "database_stable.py"}}],
            [{"type": "text", "text": "db.prod.internal"}],
        ],
    },
    default_retry_branch="use_memory_answer",
),

MemoryTask(
    task_id="v2_suff_api_key",
    category="reflection_sensitive_v2",
    dependency_level="L3",
    prompt="What is API_KEY in api_config_stable.py? Answer with just the key.",
    setup_turns=["Read api_config_stable.py. The API_KEY is sk-prod-abc123xyz789."],
    fixture_dir="reflection_sensitive_v2",
    target_files=["api_config_stable.py"],
    verifier="contains_text",
    expected_substrings=["sk-prod-abc123xyz789"],
    initial_attempt_mode="reread_first",
    optimal_retry_branch="use_memory_answer",
    retry_branches={
        "use_memory_answer": [[{"type": "text", "text": "sk-prod-abc123xyz789"}]],
        "reread_then_answer": [
            [{"type": "tool_use", "id": "c1", "name": "read", "input": {"file_path": "api_config_stable.py"}}],
            [{"type": "text", "text": "sk-prod-abc123xyz789"}],
        ],
    },
    default_retry_branch="use_memory_answer",
),

# partial_memory: setup 只给部分信息，main 需要全部
MemoryTask(
    task_id="v2_partial_config",
    category="reflection_sensitive_v2",
    dependency_level="L3",
    prompt="Return API_KEY and RATE_LIMIT from config_partial.py in this format: KEY=<value>; RATE=<value>",
    setup_turns=["Read config_partial.py. The API_KEY is sk-test-key."],
    fixture_dir="reflection_sensitive_v2",
    target_files=["config_partial.py"],
    verifier="contains_text",
    expected_substrings=["sk-test-key", "100"],
    initial_attempt_mode="memory_first",
    optimal_retry_branch="reread_then_answer",
    retry_branches={
        "use_memory_answer": [[{"type": "text", "text": "KEY=sk-test-key; RATE=unknown"}]],
        "reread_then_answer": [
            [{"type": "tool_use", "id": "c1", "name": "read", "input": {"file_path": "config_partial.py"}}],
            [{"type": "text", "text": "KEY=sk-test-key; RATE=100"}],
        ],
    },
    default_retry_branch="reread_then_answer",
),
```

### 代码改动

**1. MemoryTask 新增字段：**
```python
initial_attempt_mode: str | None = None  # "memory_first" | "reread_first" | None
optimal_retry_branch: str | None = None  # benchmark 验证用
```

**2. _build_default_script 改造：**
```python
def _build_default_script(self, task, workspace_root, use_memory=True):
    # Phase 3.2F: initial_attempt_mode 覆盖默认行为
    if task.initial_attempt_mode == "memory_first":
        should_skip_reread = True  # 即使 use_memory=False 也跳过 reread
    elif task.initial_attempt_mode == "reread_first":
        should_skip_reread = False  # 即使 use_memory=True 也执行 reread
    else:
        should_skip_reread = use_memory and task.setup_turns
    ...
```

**3. 三组对比子集更新：**
- 新增 `reflection_sensitive_v2` 子集入口
- 三组对比默认用 v2 子集（5 个任务）
- 保留旧 v1 子集（3 个任务）向后兼容

**4. JSON 输出增加 optimal_retry_branch 验证：**
- 每个 task 的 result 里记录 `selected_branch` vs `optimal_retry_branch`
- 汇总统计：prompt-sensitive 选对最优 branch 的比例

### 验收标准

- [ ] 5 个新任务在 `reflection_sensitive_v2` 子集里
- [ ] `initial_attempt_mode` 只影响 first attempt，不泄漏到 retry
- [ ] stale_memory 任务的 first attempt 确实用 memory（答错）
- [ ] memory_sufficient 任务的 first attempt 确实 reread（浪费）
- [ ] prompt-sensitive 选对了 stale → reread, suff → memory
- [ ] fixed "use_memory" 在 stale 任务上答错
- [ ] fixed "reread" 在 suff 任务上多花 tool call
- [ ] `prompt_sensitive_vs_scripted` 的 delta > 0 或 tool_calls 更优
- [ ] 不破坏 3.2E 的历史 baseline
- [ ] 全量测试继续为绿
