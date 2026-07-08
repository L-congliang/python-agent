"""Memory Experiment - 验证记忆系统的效果

实验设计:
- memory_on: 使用完整记忆系统（memory_enabled=True）
- memory_off: 不使用记忆（memory_enabled=False）
- memory_irrelevant: 使用无关记忆（噪音）

评估指标（全部来自真实运行数据）:
- correct_rate: 正确率（由 verifier 判定）
- repeated_reads: 重复读取次数（同一文件第 2 次及以后成功读取）
- memory_hit_rate: 记忆命中率（避免不必要 reread 的任务比例）
- avg_tool_calls: 平均工具调用次数
- avg_duration: 平均耗时
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import json
import logging
import os
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.evaluation.memory_experiment")

if TYPE_CHECKING:
    from agent.reflection.types import ReflectionConfig


# ============================================================
# 数据结构
# ============================================================


@dataclass
class MemoryTask:
    """记忆测试任务

    Attributes:
        task_id: 任务 ID
        category: 类别（fact_lookup, edit_dependency, history_reference, etc.）
        dependency_level: 记忆依赖等级（L1/L2/L3/L4）
            L1: 不需要记忆也能答对（如 fact_lookup）
            L2: 记忆有帮助但不是必须（如 history_reference）
            L3: 记忆显著提升效率（如 cross_round_recall）
            L4: 没有记忆几乎不可能答对（如 disambiguate, constraint）
        prompt: 主任务提示
        setup_turns: 前置对话（为 history_reference 提供上下文）
        expected_files: 预期访问的文件
        target_files: 用于 repeated_reads / memory_hit 统计的文件
        verifier: 验证方式（contains_text / exact_match / structured_match /
                  file_changed / file_changed_strict / multi_file_changed /
                  forbidden_reread / file_changed_no_extra_change）
        expected_substrings: 正确性验证的期望子串
        expected_answer: 预期精确答案（用于 exact_match）
        forbidden_reads: 主任务阶段禁止读取的文件（用于 forbidden_reread）
        allowed_files: 只允许修改的文件（用于 no_extra_changes）
        no_extra_changes: 是否检查只改了该改的文件
        fixture_dir: 该任务使用的 fixture 子目录（相对于 tests/fixtures/memory_experiment/）
        allow_reread: 是否允许重复读取
    """
    task_id: str
    category: str
    prompt: str
    dependency_level: str = "L1"
    setup_turns: list[str] = field(default_factory=list)
    expected_files: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)
    verifier: str = "contains_text"
    expected_substrings: list[str] = field(default_factory=list)
    expected_answer: str = ""
    forbidden_reads: list[str] = field(default_factory=list)
    allowed_files: list[str] = field(default_factory=list)
    no_extra_changes: bool = False
    fixture_dir: str = ""
    allow_reread: bool = False
    retry_script: list[list[dict[str, Any]]] | None = None
    retry_branches: dict[str, list[list[dict[str, Any]]]] | None = None
    default_retry_branch: str = "use_memory_answer"


@dataclass
class MemoryConfig:
    """记忆配置

    Attributes:
        name: 配置名称
        use_memory: 是否使用记忆
        use_irrelevant_memory: 是否使用无关记忆
    """
    name: str
    use_memory: bool = True
    use_irrelevant_memory: bool = False


@dataclass
class MemoryMetrics:
    """记忆指标

    指标分级（Phase 3.2E 调整）：
    - 主效果指标：avg_tool_calls, target_reread_rate, answer_without_reread_rate, memory_dependent_success_rate
    - 辅助 guardrail：correct_rate（不能因追求效率牺牲正确性）
    - 诊断指标：memory_hit_rate（只用于诊断，不作为结论依据）

    Attributes:
        repeated_reads: 重复读取次数
        correct_rate: 正确率（辅助 guardrail）
        memory_hit_rate: 记忆命中率（诊断指标，不作为主效果指标）
        memory_dependent_success_rate: 记忆依赖成功率（主效果指标：L3/L4 任务正确率）
        target_reread_rate: 目标文件重读率（主效果指标：主任务阶段重读目标文件的比例）
        answer_without_reread_rate: 无重读回答率（主效果指标：setup_turns 后不重读就能答对的比例）
        total_tool_calls: 总工具调用次数
        total_tokens: 总 token 数
        avg_tool_calls: 平均工具调用次数（主效果指标）
        avg_duration: 平均耗时
        eligible_memory_tasks: 可判定 memory_hit 的任务数
        l3l4_tasks: L3/L4 任务数量
        l3l4_correct: L3/L4 任务正确数量
    """
    repeated_reads: int = 0
    correct_rate: float = 0.0
    memory_hit_rate: float = 0.0  # 诊断指标，不作为主效果指标
    memory_dependent_success_rate: float = 0.0  # 主效果指标：L3/L4 任务正确率
    target_reread_rate: float = 0.0  # 目标文件重读率
    answer_without_reread_rate: float = 0.0  # 无重读回答率
    total_tool_calls: int = 0
    total_tokens: int = 0
    avg_tool_calls: float = 0.0
    avg_duration: float = 0.0
    eligible_memory_tasks: int = 0
    l3l4_tasks: int = 0
    l3l4_correct: int = 0
    # reflection 指标（Phase 3.2C）
    reflection_trigger_rate: float = 0.0  # 触发 reflection 的任务比例
    reflection_retry_success_rate: float = 0.0  # retry 后结果正确的比例（不是"reflection 帮助率"）
    reflection_avg_extra_tool_calls: float = 0.0  # reflection 引入的额外 tool calls
    reflection_helped_tasks: int = 0  # reflection 确实带来改善的任务数


@dataclass
class MemoryAblationResult:
    """消融实验结果

    Attributes:
        config: 配置
        metrics: 指标
        duration: 耗时
        task_results: 各任务结果
        is_abnormal: 该 config 是否有异常任务（不进正式统计）
        abnormal_count: 异常任务数量
    """
    config: MemoryConfig
    metrics: MemoryMetrics
    duration: float = 0.0
    task_results: list[dict[str, Any]] = field(default_factory=list)
    is_abnormal: bool = False
    abnormal_count: int = 0


# ============================================================
# 测试任务（基于真实 repo 文件 + fixture 文件）
# ============================================================

_FIXTURE_BASE = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "memory_experiment"

MEMORY_TASKS = [
    # --- L2: history_reference — 记忆有帮助但不是必须 ---
    MemoryTask(
        task_id="history_loop_config",
        category="history_reference",
        dependency_level="L2",
        prompt="What is the default value of max_turns in LoopConfig? Answer with just the number.",
        setup_turns=[
            "Read the file src/agent/core/loop.py and tell me what LoopConfig's max_turns default is.",
        ],
        target_files=["src/agent/core/loop.py"],
        verifier="contains_text",
        expected_substrings=["50"],
        expected_answer="50",
    ),
    MemoryTask(
        task_id="history_manager_class",
        category="history_reference",
        dependency_level="L2",
        prompt="What methods does MemoryManager have? List them.",
        setup_turns=[
            "Read src/agent/memory/manager.py and describe the MemoryManager class.",
        ],
        target_files=["src/agent/memory/manager.py"],
        verifier="contains_text",
        expected_substrings=["set_task"],
    ),

    # --- L1: edit_dependency — 不需要记忆也能答对 ---
    MemoryTask(
        task_id="edit_main_function",
        category="edit_dependency",
        dependency_level="L1",
        prompt="In main.py, change the calculate_sum function to also accept an optional third "
               "parameter 'c' with default 0, and add it to the sum. Then read utils.py to check "
               "if format_output needs any update.",
        fixture_dir=".",
        target_files=["main.py", "utils.py"],
        verifier="file_changed",
        expected_substrings=["c: int = 0"],
    ),
    MemoryTask(
        task_id="edit_config_update",
        category="edit_dependency",
        dependency_level="L2",
        prompt="Read config.json, then update main.py to use the 'max_items' value from config.json "
               "as the default for a new parameter in calculate_sum.",
        fixture_dir=".",
        target_files=["main.py", "config.json"],
        verifier="file_changed",
        expected_substrings=["max_items"],
    ),

    # --- L3: cross_round_recall — 记忆显著提升效率 ---
    MemoryTask(
        task_id="recall_api_key",
        category="cross_round_recall",
        dependency_level="L3",
        prompt="What is the exact API_KEY value in api_config.py? "
               "Answer with just the key string, nothing else.",
        setup_turns=[
            "Read api_config.py and list all configuration values.",
        ],
        fixture_dir=".",
        target_files=["api_config.py"],
        verifier="exact_match",
        expected_substrings=["sk-prod-abc123xyz789"],
        expected_answer="sk-prod-abc123xyz789",
    ),
    MemoryTask(
        task_id="recall_rate_limit",
        category="cross_round_recall",
        dependency_level="L3",
        prompt="What is the RATE_LIMIT value in api_config.py? Answer with just the number.",
        setup_turns=[
            "Read api_config.py and summarize the configuration.",
        ],
        fixture_dir=".",
        target_files=["api_config.py"],
        verifier="exact_match",
        expected_substrings=["100"],
        expected_answer="100",
    ),

    # --- L3: cross_file_dep — 跨文件依赖修改 ---
    MemoryTask(
        task_id="dep_use_api_key",
        category="cross_file_dep",
        dependency_level="L3",
        prompt="Read config2.py to get the API_KEY value, then update api2.py so that "
               "DEFAULT_HEADERS uses the API_KEY directly as a string literal instead of "
               "importing it. Write the actual key value into the file.",
        setup_turns=[
            "Read config2.py and api2.py. Tell me what API_KEY is and how it's used.",
        ],
        fixture_dir=".",
        target_files=["api2.py", "config2.py"],
        verifier="file_changed_strict",
        expected_substrings=["sk-internal-KEY-9999"],
        forbidden_reads=["config2.py"],
    ),
    MemoryTask(
        task_id="dep_update_header",
        category="cross_file_dep",
        dependency_level="L3",
        prompt="Update api2.py: add a new function check_auth() that returns True if "
               "DEFAULT_HEADERS contains the correct API_KEY from config2.py. "
               "You already know the key from our earlier conversation.",
        setup_turns=[
            "Read config2.py and api2.py together. What's the API_KEY and how is DEFAULT_HEADERS built?",
        ],
        fixture_dir=".",
        target_files=["api2.py"],
        verifier="file_changed",
        expected_substrings=["check_auth"],
        forbidden_reads=["config2.py"],
    ),

    # --- L2: multi_round_edit — 多轮连续改动 ---
    MemoryTask(
        task_id="multi_add_timeout",
        category="multi_round_edit",
        dependency_level="L2",
        prompt="Do these 3 edits in order:\n"
               "1. In service.py, add a TIMEOUT constant = 30 at the top, and add a "
               "'timeout' parameter (default TIMEOUT) to process_request.\n"
               "2. In client.py, update send_request to pass a timeout keyword argument.\n"
               "3. In client.py, add a new function send_with_retry that calls send_request "
               "up to 3 times if it returns an error.",
        setup_turns=[
            "Read service.py and client.py. Describe the current function signatures.",
        ],
        fixture_dir=".",
        target_files=["service.py", "client.py"],
        verifier="multi_file_changed",
        expected_substrings=["send_with_retry"],
    ),
    MemoryTask(
        task_id="multi_add_validation",
        category="multi_round_edit",
        dependency_level="L2",
        prompt="Do these 3 edits:\n"
               "1. In service.py, change validate_input to also check that 'data' has "
               "a 'name' key (return False if missing).\n"
               "2. In client.py, update batch_send to skip items where validate_input "
               "returns False (don't add them to results).\n"
               "3. In client.py, add a function validate_batch(items) that returns the "
               "count of valid items.",
        setup_turns=[
            "Read service.py and client.py. How does validate_input work? How does batch_send use it?",
        ],
        fixture_dir=".",
        target_files=["service.py", "client.py"],
        verifier="multi_file_changed",
        expected_substrings=["validate_batch"],
    ),

    # --- L2: noise — 噪声干扰与错误纠偏 ---
    MemoryTask(
        task_id="noise_db_config",
        category="noise",
        dependency_level="L2",
        prompt="What is the DB_PASSWORD value in database.py? "
               "Answer with just the password string.",
        setup_turns=[
            "Read cache.py and tell me all the cache configuration values.",
        ],
        fixture_dir=".",
        target_files=["database.py"],
        verifier="exact_match",
        expected_substrings=["db-secret-pass-12345"],
        expected_answer="db-secret-pass-12345",
    ),
    MemoryTask(
        task_id="noise_cache_port",
        category="noise",
        dependency_level="L2",
        prompt="What is the CACHE_PORT value in cache.py? Answer with just the number.",
        setup_turns=[
            "Read database.py and tell me all the database configuration values.",
        ],
        fixture_dir=".",
        target_files=["cache.py"],
        verifier="exact_match",
        expected_substrings=["6379"],
        expected_answer="6379",
    ),

    # --- V2: 高记忆依赖任务 ---

    # L4: 抗混淆任务 — setup 读了两个相似文件，主任务要求只返回其中一个
    MemoryTask(
        task_id="disambiguate_db_vs_cache_secret",
        category="noise",
        dependency_level="L4",
        prompt="Return only the DB_PASSWORD value, not the cache password.",
        setup_turns=[
            "Read database.py and cache.py, then tell me the DB password and cache password separately.",
        ],
        fixture_dir=".",
        target_files=["database.py", "cache.py"],
        verifier="exact_match",
        expected_substrings=["db-secret-pass-12345"],
        expected_answer="db-secret-pass-12345",
    ),

    # L4: 记住约束 — setup 阶段给约束，主任务要求遵守
    MemoryTask(
        task_id="delayed_constraint_single_file_edit",
        category="edit_dependency",
        dependency_level="L4",
        prompt="Add a new function send_safe(payload) to client.py. It should call "
               "validate_input first and return {'error': 'invalid input'} if validation "
               "fails; otherwise call process_request. Do not modify service.py.",
        setup_turns=[
            "Read service.py and client.py. Important constraint: later you may only "
            "modify client.py, do not modify service.py.",
        ],
        fixture_dir=".",
        target_files=["client.py", "service.py"],
        verifier="file_changed_no_extra_change",
        expected_substrings=["send_safe"],
        allowed_files=["client.py"],
        no_extra_changes=True,
    ),

    # L4: 跨文件精确回忆 + 无 import 编辑
    MemoryTask(
        task_id="cross_file_literal_recall_no_import",
        category="cross_file_dep",
        dependency_level="L4",
        prompt="Update api2.py so it defines DEFAULT_LIMIT = the exact MAX_ITEMS integer "
               "from config2.py, and add a function build_auth_header() that returns the "
               "exact Bearer token string using the API_KEY value as a literal. Do not "
               "import any new symbol from config2.py.",
        setup_turns=[
            "Read config2.py and api2.py. Remember the exact API_KEY and MAX_ITEMS values.",
        ],
        fixture_dir=".",
        target_files=["api2.py", "config2.py"],
        verifier="file_changed_strict",
        expected_substrings=["DEFAULT_LIMIT", "200", "build_auth_header", "sk-internal-KEY-9999"],
        forbidden_reads=["config2.py"],
        allowed_files=["api2.py"],
        no_extra_changes=True,
    ),

    # L4: 插入噪声后继续前任务
    MemoryTask(
        task_id="multi_round_edit_after_noise",
        category="multi_round_edit",
        dependency_level="L4",
        prompt="Continue the earlier service/client task: in service.py add TIMEOUT = 30 "
               "and make process_request accept timeout=TIMEOUT; in client.py make "
               "send_request pass timeout, and add send_with_retry(payload, retries=3). "
               "Ignore the database/cache info.",
        setup_turns=[
            "Read service.py and client.py. Describe current function signatures.",
            "Now read database.py and cache.py and summarize them briefly.",
        ],
        fixture_dir=".",
        target_files=["service.py", "client.py"],
        verifier="multi_file_changed",
        expected_substrings=["send_with_retry"],
    ),

    # L3: 禁止 reread 的事实回答
    MemoryTask(
        task_id="forbidden_reread_fact_answer",
        category="cross_round_recall",
        dependency_level="L3",
        prompt="What is the TIMEOUT value? Answer with just the number.",
        setup_turns=[
            "Read api_config.py and memorize API_KEY, API_URL, and TIMEOUT.",
        ],
        fixture_dir=".",
        target_files=["api_config.py"],
        verifier="forbidden_reread",
        expected_substrings=["30"],
        expected_answer="30",
        forbidden_reads=["api_config.py"],
    ),

    # L4: 用前置事实编辑，不 reread
    MemoryTask(
        task_id="edit_using_previous_fact_only",
        category="edit_dependency",
        dependency_level="L4",
        prompt="Update main.py by adding DEFAULT_RATE_LIMIT and DEFAULT_RETRY_COUNT "
               "constants at the top using the exact values from earlier context. "
               "Do not read api_config.py again.",
        setup_turns=[
            "Read api_config.py and tell me the exact RATE_LIMIT and RETRY_COUNT values.",
        ],
        fixture_dir=".",
        target_files=["main.py", "api_config.py"],
        verifier="file_changed_strict",
        expected_substrings=["100", "3"],
        forbidden_reads=["api_config.py"],
        allowed_files=["main.py"],
        no_extra_changes=True,
    ),

    # === V4-A: 高难度 L3/L4 任务 ===

    # L4: edit_using_previous_fact_only 的强化版 — 双常量精确写入
    MemoryTask(
        task_id="delayed_dual_constant_edit",
        category="edit_dependency",
        dependency_level="L4",
        prompt="Update main.py by adding DEFAULT_RATE_LIMIT and DEFAULT_RETRY_COUNT "
               "constants at the top using the exact earlier values. "
               "Do not read api_config.py again.",
        setup_turns=[
            "Read api_config.py and tell me the exact RATE_LIMIT and RETRY_COUNT values.",
        ],
        fixture_dir=".",
        target_files=["main.py"],
        verifier="file_changed_strict",
        expected_substrings=["DEFAULT_RATE_LIMIT = 100", "DEFAULT_RETRY_COUNT = 3"],
        forbidden_reads=["api_config.py"],
        allowed_files=["main.py"],
        no_extra_changes=True,
    ),

    # L4: 冲突信息精确取两项 — 减少蒙对概率
    MemoryTask(
        task_id="conflict_secret_disambiguation_strict",
        category="noise",
        dependency_level="L4",
        prompt='Return a JSON object with exactly two fields: '
               '{"db_password": "...", "cache_port": ...}. '
               "Do not include cache password or db port.",
        setup_turns=[
            "Read database.py and cache.py. "
            "Summarize DB_PASSWORD, CACHE_PASSWORD, DB_PORT, and CACHE_PORT separately.",
        ],
        fixture_dir=".",
        target_files=["database.py", "cache.py"],
        verifier="structured_match",
        expected_substrings=['"db_password"', 'db-secret-pass-12345', '"cache_port"', '6379'],
    ),

    # L4: 跨文件字面量捆绑回忆 + 无 import 编辑
    MemoryTask(
        task_id="cross_file_literal_bundle_no_reread",
        category="cross_file_dep",
        dependency_level="L4",
        prompt="Update api2.py so it defines DEFAULT_LIMIT using the exact MAX_ITEMS "
               "literal and adds build_auth_header() returning the exact Bearer token "
               "string. Do not read config2.py again and do not add new imports.",
        setup_turns=[
            "Read config2.py and api2.py. Remember the exact API_KEY and MAX_ITEMS values.",
        ],
        fixture_dir=".",
        target_files=["api2.py"],
        verifier="file_changed_no_extra_change",
        expected_substrings=["DEFAULT_LIMIT = 200", "Bearer sk-internal-KEY-9999", "build_auth_header"],
        forbidden_reads=["config2.py"],
        allowed_files=["api2.py"],
        no_extra_changes=True,
    ),

    # L4: 噪声后继续主线任务 — 测记忆抗干扰能力
    MemoryTask(
        task_id="resume_multi_edit_after_irrelevant_round",
        category="multi_round_edit",
        dependency_level="L4",
        prompt="Continue the earlier service/client refactor only: in service.py add "
               "TIMEOUT = 30 and make process_request accept timeout=TIMEOUT; in client.py "
               "pass timeout in send_request and add send_with_retry(payload, retries=3). "
               "Ignore the database/cache information.",
        setup_turns=[
            "Read service.py and client.py. Describe how validate_input, process_request, "
            "send_request, and batch_send currently work.",
            "Now read database.py and cache.py and summarize them.",
        ],
        fixture_dir=".",
        target_files=["service.py", "client.py"],
        verifier="multi_file_changed",
        expected_substrings=["TIMEOUT = 30", "timeout", "send_with_retry"],
    ),

    # L4: 延迟约束保持 — 主要测约束记忆而非代码能力
    MemoryTask(
        task_id="constraint_then_edit_single_target",
        category="edit_dependency",
        dependency_level="L4",
        prompt="Add send_safe(payload) to client.py. It should validate input first, "
               "then call process_request, and return {'error': 'invalid input'} if "
               "validation fails.",
        setup_turns=[
            "Read service.py and client.py. Important later constraint: you may only "
            "modify client.py, never modify service.py.",
        ],
        fixture_dir=".",
        target_files=["client.py"],
        verifier="file_changed_no_extra_change",
        expected_substrings=["send_safe", "invalid input"],
        allowed_files=["client.py"],
        no_extra_changes=True,
    ),

    # L3: 多字段禁止 reread — 比单值 recall 更难
    MemoryTask(
        task_id="forbidden_reread_multi_fact_answer",
        category="cross_round_recall",
        dependency_level="L3",
        prompt="Return exactly this format: API_URL=<value>; TIMEOUT=<value>; "
               "RETRY_COUNT=<value>. Do not read api_config.py again.",
        setup_turns=[
            "Read api_config.py and memorize API_URL, RATE_LIMIT, TIMEOUT, and RETRY_COUNT.",
        ],
        fixture_dir=".",
        target_files=["api_config.py"],
        verifier="forbidden_reread",
        expected_substrings=[
            "API_URL=https://api.production.internal/v2",
            "TIMEOUT=30",
            "RETRY_COUNT=3",
        ],
        forbidden_reads=["api_config.py"],
    ),

    # --- L3: memory_sensitive — memory_on 跳过 reread，memory_off 必须 reread ---
    # 这些任务专门设计为 memory 敏感：
    # memory_on: 从 setup_turns 记住信息，主任务直接回答（0 tool_calls）
    # memory_off: 需要 reread 文件才能回答（1 tool_call）
    MemoryTask(
        task_id="mem_sensitive_api_url",
        category="memory_sensitive",
        dependency_level="L3",
        prompt="What is the API_URL value from the project config? "
               "Answer with just the URL, no explanation.",
        setup_turns=[
            "Read api_config.py and tell me the API_URL value.",
        ],
        fixture_dir=".",
        target_files=["api_config.py"],
        verifier="contains_text",
        expected_substrings=["https://api.production.internal/v2"],
        # retry_branches: 多路径 retry（Phase 3.2F prompt-sensitive）
        retry_branches={
            "use_memory_answer": [
                [{"type": "text", "text": "https://api.production.internal/v2"}],
            ],
            "reread_then_answer": [
                [{"type": "tool_use", "id": "call_1", "name": "read",
                  "input": {"file_path": "api_config.py"}}],
                [{"type": "text", "text": "https://api.production.internal/v2"}],
            ],
        },
        default_retry_branch="use_memory_answer",
    ),
    MemoryTask(
        task_id="mem_sensitive_db_host",
        category="memory_sensitive",
        dependency_level="L3",
        prompt="What is the DB_HOST value from database.py? "
               "Answer with just the hostname.",
        setup_turns=[
            "Read database.py and tell me the DB_HOST value.",
        ],
        fixture_dir=".",
        target_files=["database.py"],
        verifier="contains_text",
        expected_substrings=["db.prod.internal"],
        retry_branches={
            "use_memory_answer": [
                [{"type": "text", "text": "db.prod.internal"}],
            ],
            "reread_then_answer": [
                [{"type": "tool_use", "id": "call_1", "name": "read",
                  "input": {"file_path": "database.py"}}],
                [{"type": "text", "text": "db.prod.internal"}],
            ],
        },
        default_retry_branch="use_memory_answer",
    ),
    MemoryTask(
        task_id="mem_sensitive_cache_port",
        category="memory_sensitive",
        dependency_level="L3",
        prompt="What is the CACHE_PORT value from cache.py? "
               "Answer with just the port number.",
        setup_turns=[
            "Read cache.py and tell me the CACHE_PORT value.",
        ],
        fixture_dir=".",
        target_files=["cache.py"],
        verifier="contains_text",
        expected_substrings=["6379"],
        retry_branches={
            "use_memory_answer": [
                [{"type": "text", "text": "6379"}],
            ],
            "reread_then_answer": [
                [{"type": "tool_use", "id": "call_1", "name": "read",
                  "input": {"file_path": "cache.py"}}],
                [{"type": "text", "text": "6379"}],
            ],
        },
        default_retry_branch="use_memory_answer",
    ),
]


# ============================================================
# AgentLoop 工厂
# ============================================================


def _create_real_agent_loop(
    memory_enabled: bool = True,
    workspace_root: str | None = None,
    max_turns: int = 15,
):
    """创建真实的 AgentLoop

    Args:
        memory_enabled: 是否启用记忆系统
        workspace_root: 工作区根目录
        max_turns: 最大轮次

    Returns:
        AgentLoop 实例
    """
    from agent.core.model import MimoClient, ModelConfig
    from agent.core.loop import AgentLoop, LoopConfig
    from agent.tools.registry import ToolRegistry
    from agent.tools.bash import bash_tool
    from agent.tools.file_read import file_read_tool
    from agent.tools.file_write import file_write_tool
    from agent.tools.file_edit import file_edit_tool
    from agent.tools.grep import grep_tool
    from agent.tools.glob import glob_tool

    api_key = os.environ.get("MIMO_API_KEY", "")
    base_url = os.environ.get(
        "MIMO_BASE_URL",
        "https://token-plan-cn.xiaomimimo.com/anthropic",
    )
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

    if not api_key:
        raise ValueError("MIMO_API_KEY not set. Export it or pass via environment.")

    config = ModelConfig(api_key=api_key, base_url=base_url, model=model)
    client = MimoClient(config)

    registry = ToolRegistry()
    registry.register(bash_tool)
    registry.register(file_read_tool)
    registry.register(file_write_tool)
    registry.register(file_edit_tool)
    registry.register(grep_tool)
    registry.register(glob_tool)

    loop_config = LoopConfig(
        model=config.model,
        max_turns=max_turns,
        system_prompt="You are a helpful coding assistant. Answer concisely.",
        memory_enabled=memory_enabled,
        workspace_root=workspace_root,
    )

    return AgentLoop(client, registry, config=loop_config)


def _create_agent_loop_with_client(
    client: Any,
    memory_enabled: bool = True,
    workspace_root: str | None = None,
    max_turns: int = 15,
):
    """用指定 client 创建 AgentLoop（支持 FakeModelClient / ScriptedModelClient）

    与 _create_real_agent_loop 的区别：不创建 MimoClient，直接用传入的 client。
    不需要 MIMO_API_KEY。

    Args:
        client: 模型客户端（FakeModelClient / ScriptedModelClient / MimoClient）
        memory_enabled: 是否启用记忆系统
        workspace_root: 工作区根目录
        max_turns: 最大轮次

    Returns:
        AgentLoop 实例
    """
    from agent.core.loop import AgentLoop, LoopConfig
    from agent.tools.registry import ToolRegistry
    from agent.tools.bash import bash_tool
    from agent.tools.file_read import file_read_tool
    from agent.tools.file_write import file_write_tool
    from agent.tools.file_edit import file_edit_tool
    from agent.tools.grep import grep_tool
    from agent.tools.glob import glob_tool

    registry = ToolRegistry()
    registry.register(bash_tool)
    registry.register(file_read_tool)
    registry.register(file_write_tool)
    registry.register(file_edit_tool)
    registry.register(grep_tool)
    registry.register(glob_tool)

    loop_config = LoopConfig(
        model="scripted-eval",
        max_turns=max_turns,
        system_prompt="You are a helpful coding assistant. Answer concisely.",
        memory_enabled=memory_enabled,
        workspace_root=workspace_root,
    )

    return AgentLoop(client, registry, config=loop_config)


# ============================================================
# 验证器
# ============================================================


def _verify_task_result(
    task: MemoryTask,
    result_text: str,
    workspace_root: str,
    tool_history: list[dict[str, Any]] | None = None,
) -> bool:
    """验证任务结果

    Args:
        task: 任务定义
        result_text: 模型最终回复
        workspace_root: 工作区根目录
        tool_history: 工具执行历史（用于 forbidden_reread 检查）

    Returns:
        是否正确
    """
    if task.verifier == "contains_text":
        result_lower = result_text.lower()
        return all(sub.lower() in result_lower for sub in task.expected_substrings)

    if task.verifier == "exact_match":
        # 精确匹配：回复中必须包含 expected_answer（如果提供）或所有 expected_substrings
        result_stripped = result_text.strip()
        if task.expected_answer:
            # 优先使用 expected_answer 进行精确匹配
            return task.expected_answer in result_stripped
        return all(sub in result_stripped for sub in task.expected_substrings)

    if task.verifier == "structured_match":
        # 结构化匹配：回复必须包含所有 expected_substrings，且格式正确
        result_stripped = result_text.strip()
        if not all(sub in result_stripped for sub in task.expected_substrings):
            return False
        # 检查是否包含预期的结构（如列表、表格等）
        # 简单检查：回复长度合理，不是空回复
        return len(result_stripped) > 10

    if task.verifier == "file_changed":
        for target in task.target_files:
            file_path = os.path.join(workspace_root, target)
            if not os.path.exists(file_path):
                continue
            try:
                content = Path(file_path).read_text(encoding="utf-8")
                if any(sub in content for sub in task.expected_substrings):
                    return True
            except OSError:
                continue
        return False

    if task.verifier == "file_changed_strict":
        # 严格文件变更：所有 target_files 都必须存在，
        # 且所有 expected_substrings 都必须在文件内容中出现
        for target in task.target_files:
            file_path = os.path.join(workspace_root, target)
            if not os.path.exists(file_path):
                return False
        all_content = ""
        for target in task.target_files:
            file_path = os.path.join(workspace_root, target)
            try:
                all_content += Path(file_path).read_text(encoding="utf-8")
            except OSError:
                return False
        return all(sub in all_content for sub in task.expected_substrings)

    if task.verifier == "multi_file_changed":
        changed = 0
        for target in task.target_files:
            file_path = os.path.join(workspace_root, target)
            if os.path.exists(file_path):
                changed += 1
        return changed >= 2

    if task.verifier == "forbidden_reread":
        # 禁止 reread：答案正确且主任务阶段未 reread 目标文件
        # 首先检查答案是否正确
        result_lower = result_text.lower()
        if not all(sub.lower() in result_lower for sub in task.expected_substrings):
            return False
        # 然后检查是否 reread 了禁止的文件
        if tool_history and task.forbidden_reads:
            for entry in tool_history:
                if entry.get("tool_name") != "read":
                    continue
                if entry.get("is_error"):
                    continue
                resolved = entry.get("resolved_path", "")
                if not resolved:
                    continue
                # 检查是否读取了禁止的文件
                for forbidden in task.forbidden_reads:
                    forbidden_abs = os.path.normpath(os.path.join(workspace_root, forbidden))
                    if os.path.normpath(resolved) == forbidden_abs:
                        return False
        return True

    if task.verifier == "file_changed_no_extra_change":
        # 新文件变更 + 原文件未改动
        # expected_substrings 必须在新文件中出现
        # 检查 allowed_files 中的文件被修改，其他文件未被修改
        if not task.allowed_files:
            # 如果没有指定 allowed_files，使用传统逻辑
            if len(task.target_files) < 2:
                return False
            new_file = task.target_files[0]
            old_file = task.target_files[1]
            new_path = os.path.join(workspace_root, new_file)
            old_path = os.path.join(workspace_root, old_file)
            if not os.path.exists(new_path):
                return False
            try:
                new_content = Path(new_path).read_text(encoding="utf-8")
                if not all(sub in new_content for sub in task.expected_substrings):
                    return False
            except OSError:
                return False
            if os.path.exists(old_path):
                try:
                    old_content = Path(old_path).read_text(encoding="utf-8")
                    if any(sub in old_content for sub in task.expected_substrings):
                        return False
                except OSError:
                    pass
            return True
        else:
            # 使用 allowed_files 检查
            # 1. 检查 allowed_files 中的文件包含 expected_substrings
            for allowed in task.allowed_files:
                allowed_path = os.path.join(workspace_root, allowed)
                if not os.path.exists(allowed_path):
                    return False
                try:
                    content = Path(allowed_path).read_text(encoding="utf-8")
                    if not all(sub in content for sub in task.expected_substrings):
                        return False
                except OSError:
                    return False
            # 2. 检查 target_files 中不在 allowed_files 的文件未被修改
            # 这里用简单方法：检查这些文件是否仍然存在且不包含 expected_substrings
            for target in task.target_files:
                if target in task.allowed_files:
                    continue
                target_path = os.path.join(workspace_root, target)
                if os.path.exists(target_path):
                    try:
                        content = Path(target_path).read_text(encoding="utf-8")
                        if any(sub in content for sub in task.expected_substrings):
                            return False
                    except OSError:
                        pass
            return True

    # 未知 verifier，默认通过
    return True


def _count_repeated_reads(
    tool_history: list[dict[str, Any]],
    target_files: list[str],
    workspace_root: str,
) -> int:
    """统计重复读取次数

    定义：同一 loop 内，对同一 resolved_path 的第 2 次及以后成功 read，计为 repeated_read。
    注意：这与"setup 后是否 reread 目标文件"是不同的语义，后者用 _check_target_reread。

    Args:
        tool_history: 工具执行历史
        target_files: 目标文件列表（相对路径）
        workspace_root: 工作区根目录

    Returns:
        重复读取次数
    """
    if not target_files:
        return 0

    # 构建目标文件的绝对路径集合
    target_abs = set()
    for f in target_files:
        target_abs.add(os.path.normpath(os.path.join(workspace_root, f)))

    read_counts: Counter[str] = Counter()
    for entry in tool_history:
        if entry.get("tool_name") != "read":
            continue
        if entry.get("is_error"):
            continue
        if entry.get("blocked_by_repeat_detector"):
            continue
        resolved = entry.get("resolved_path", "")
        if not resolved:
            continue
        resolved = os.path.normpath(resolved)
        if target_abs and resolved not in target_abs:
            continue
        read_counts[resolved] += 1

    # 每个文件第 2 次及以后的读取算重复
    return sum(count - 1 for count in read_counts.values() if count > 1)


def _compute_memory_hit(
    task: MemoryTask,
    tool_history: list[dict[str, Any]],
    workspace_root: str,
) -> int:
    """计算 memory_hit

    定义：对于有 setup_turns 的任务，如果主任务阶段没有再次 read 已在 setup 阶段
    读过的目标文件，则记 1；否则记 0。

    Args:
        task: 任务定义
        tool_history: 工具执行历史
        workspace_root: 工作区根目录

    Returns:
        0 或 1
    """
    if not task.setup_turns:
        # 没有 setup_turns 的任务不算 eligible
        return -1  # 表示不计入统计

    if not task.target_files:
        return -1

    # 构建目标文件的绝对路径集合
    target_abs = set()
    for f in task.target_files:
        target_abs.add(os.path.normpath(os.path.join(workspace_root, f)))

    # 统计主任务阶段（tool_history 在 setup_turns 后已清空，
    # 此处只有主任务阶段的工具调用）
    main_reads: set[str] = set()
    for entry in tool_history:
        if entry.get("tool_name") != "read":
            continue
        if entry.get("is_error"):
            continue
        resolved = entry.get("resolved_path", "")
        if not resolved:
            continue
        resolved = os.path.normpath(resolved)
        if target_abs and resolved in target_abs:
            main_reads.add(resolved)

    # 如果主任务阶段没有读取任何目标文件 → memory_hit（记忆避免了 reread）
    return 1 if len(main_reads) == 0 else 0


def _check_target_reread(
    task: MemoryTask,
    tool_history: list[dict[str, Any]],
    workspace_root: str,
) -> bool:
    """检查主任务阶段是否读取了目标文件（setup 后 reread 语义）

    与 _count_repeated_reads 的区别：
    - _count_repeated_reads: 同一 loop 内第 2 次+ 读取
    - _check_target_reread: 主任务阶段是否读了目标文件（不管第几次）

    用于 target_reread_rate 和 answer_without_reread_rate 的统计。

    Args:
        task: 任务定义
        tool_history: 主任务阶段的工具执行历史
        workspace_root: 工作区根目录

    Returns:
        True if 主任务阶段读取了任何目标文件
    """
    if not task.target_files:
        return False

    target_abs = set()
    for f in task.target_files:
        target_abs.add(os.path.normpath(os.path.join(workspace_root, f)))

    for entry in tool_history:
        if entry.get("tool_name") != "read":
            continue
        if entry.get("is_error"):
            continue
        resolved = entry.get("resolved_path", "")
        if not resolved:
            continue
        resolved = os.path.normpath(resolved)
        if resolved in target_abs:
            return True

    return False


# ============================================================
# 实验主类
# ============================================================


class MemoryExperiment:
    """记忆实验

    使用方式:
        experiment = MemoryExperiment(use_real_model=True)
        results = experiment.run()
        report = experiment.generate_report(results)
    """

    def __init__(
        self,
        output_dir: str | Path | None = None,
        max_turns: int = 15,
        use_real_model: bool = False,
    ) -> None:
        """初始化

        Args:
            output_dir: 输出目录
            max_turns: 每个任务最大轮次
            use_real_model: 是否使用真实模型
        """
        if output_dir is None:
            output_dir = Path.cwd() / "docs" / "test-reports"
        self._output_dir = Path(output_dir)
        self._max_turns = max_turns
        self._use_real_model = use_real_model

        self._configs = [
            MemoryConfig(name="memory_on", use_memory=True),
            MemoryConfig(name="memory_off", use_memory=False),
            MemoryConfig(name="memory_irrelevant", use_memory=True, use_irrelevant_memory=True),
        ]

    def run(
        self,
        tasks: list[MemoryTask] | None = None,
        reflection_config: ReflectionConfig | None = None,
    ) -> list[MemoryAblationResult]:
        """运行实验

        Args:
            tasks: 测试任务列表，默认使用 MEMORY_TASKS
            reflection_config: reflection 配置（None = 不启用 reflection）

        Returns:
            各配置的实验结果
        """
        if tasks is None:
            tasks = MEMORY_TASKS

        results = []
        for i, config in enumerate(self._configs):
            logger.info("Running config: %s", config.name)
            result = self._run_single_config(config, tasks, reflection_config)
            results.append(result)

            # 配置间延迟（从 15s 提升到 45s）
            if i < len(self._configs) - 1 and self._use_real_model:
                time.sleep(45)

        return results

    def _run_single_config(
        self,
        config: MemoryConfig,
        tasks: list[MemoryTask],
        reflection_config: ReflectionConfig | None = None,
    ) -> MemoryAblationResult:
        """运行单个配置"""
        start_time = time.time()
        task_results = []
        total_repeated_reads = 0
        total_correct = 0
        total_memory_hits = 0
        total_tool_calls = 0
        total_duration = 0.0
        eligible_memory_tasks = 0
        abnormal_count = 0
        # 新增指标统计
        l3l4_tasks = 0
        l3l4_correct = 0
        target_reread_count = 0
        answer_without_reread_count = 0
        tasks_with_setup = 0  # 有 setup_turns 的任务数（target_reread_rate 的分母）
        # reflection 指标统计
        reflection_triggered_count = 0
        reflection_success_count = 0
        reflection_extra_tool_calls = 0
        reflection_helped_count = 0  # reflection 确实带来改善的任务数

        for i, task in enumerate(tasks):
            logger.info("  Running task: %s", task.task_id)
            result = self._run_single_task(config, task, reflection_config)
            task_results.append(result)

            # 统计异常任务
            if result.get("is_abnormal", False):
                abnormal_count += 1

            total_repeated_reads += result.get("repeated_reads", 0)
            if result.get("correct", False):
                total_correct += 1
            total_tool_calls += result.get("tool_calls", 0)
            total_duration += result.get("duration", 0.0)

            mh = result.get("memory_hits", -1)
            if mh >= 0:
                total_memory_hits += mh
                eligible_memory_tasks += 1

            # 统计 L3/L4 任务
            if task.dependency_level in ("L3", "L4"):
                l3l4_tasks += 1
                if result.get("correct", False):
                    l3l4_correct += 1

            # 统计目标文件重读率（有 setup_turns 的任务中，主任务阶段读了目标文件的比例）
            if task.setup_turns:
                tasks_with_setup += 1
                if result.get("read_target_after_setup", False):
                    target_reread_count += 1

            # 统计无重读回答率（有 setup_turns + 正确 + 主任务没再读目标文件）
            if task.setup_turns and result.get("correct", False) and not result.get("read_target_after_setup", False):
                answer_without_reread_count += 1

            # 统计 reflection 指标
            if result.get("reflection_triggered", False):
                reflection_triggered_count += 1
                if result.get("correct", False):
                    reflection_success_count += 1
                # 额外 tool calls = total - first_attempt
                first_tools = result.get("first_attempt_tool_calls", 0)
                total_tools = result.get("tool_calls", 0)
                reflection_extra_tool_calls += max(0, total_tools - first_tools)
                # reflection 帮助判定：
                # first attempt 的状态
                first_correct = result.get("first_attempt_correct", False)
                first_reread = result.get("first_attempt_read_target", False)
                # retry 后的状态（result 的 read_target_after_setup 已是 retry 后的值）
                retry_correct = result.get("correct", False)
                retry_reread = result.get("read_target_after_setup", False)
                helped = False
                if not first_correct and retry_correct:
                    helped = True  # 从错变对
                if first_reread and not retry_reread:
                    helped = True  # 从 reread 变不 reread
                if helped:
                    reflection_helped_count += 1

            # 任务间延迟，避免 429（从 8s 提升到 15s）
            if i < len(tasks) - 1 and self._use_real_model:
                time.sleep(15)

        duration = time.time() - start_time
        n = len(tasks) if tasks else 1

        # 计算新指标
        memory_dependent_success_rate = l3l4_correct / l3l4_tasks if l3l4_tasks > 0 else 0.0
        # target_reread_rate: 分母用有 setup_turns 的任务数
        target_reread_rate = target_reread_count / tasks_with_setup if tasks_with_setup > 0 else 0.0
        # answer_without_reread_rate: 分母也用有 setup_turns 的任务数
        answer_without_reread_rate = answer_without_reread_count / tasks_with_setup if tasks_with_setup > 0 else 0.0
        # reflection 指标
        reflection_trigger_rate = reflection_triggered_count / n if n > 0 else 0.0
        reflection_retry_success_rate = reflection_success_count / reflection_triggered_count if reflection_triggered_count > 0 else 0.0
        reflection_avg_extra_tool_calls = reflection_extra_tool_calls / reflection_triggered_count if reflection_triggered_count > 0 else 0.0

        metrics = MemoryMetrics(
            repeated_reads=total_repeated_reads,
            correct_rate=total_correct / n,
            memory_hit_rate=total_memory_hits / eligible_memory_tasks if eligible_memory_tasks > 0 else 0.0,
            memory_dependent_success_rate=memory_dependent_success_rate,
            target_reread_rate=target_reread_rate,
            answer_without_reread_rate=answer_without_reread_rate,
            total_tool_calls=total_tool_calls,
            avg_tool_calls=total_tool_calls / n,
            avg_duration=total_duration / n,
            eligible_memory_tasks=eligible_memory_tasks,
            l3l4_tasks=l3l4_tasks,
            l3l4_correct=l3l4_correct,
            reflection_trigger_rate=reflection_trigger_rate,
            reflection_retry_success_rate=reflection_retry_success_rate,
            reflection_avg_extra_tool_calls=reflection_avg_extra_tool_calls,
            reflection_helped_tasks=reflection_helped_count,
        )

        # config 级异常判定：有异常任务的 config 不进正式统计
        is_abnormal = abnormal_count > 0

        return MemoryAblationResult(
            config=config,
            metrics=metrics,
            duration=duration,
            task_results=task_results,
            is_abnormal=is_abnormal,
            abnormal_count=abnormal_count,
        )

    def _run_single_task(
        self,
        config: MemoryConfig,
        task: MemoryTask,
        reflection_config: ReflectionConfig | None = None,
    ) -> dict[str, Any]:
        """运行单个任务

        use_real_model=True: 用真实 MimoClient 驱动 AgentLoop
        use_real_model=False: 用 ScriptedModelClient 驱动真实 AgentLoop
            （替代原来的 _run_mock_task 常量返回路径）
        """
        if not self._use_real_model:
            return self._run_scripted_task(config, task, reflection_config)

        return self._run_real_task(config, task)

    def _run_mock_task(
        self,
        config: MemoryConfig,
        task: MemoryTask,
    ) -> dict[str, Any]:
        """模拟运行（用于框架测试，保留向后兼容）"""
        return {
            "task_id": task.task_id,
            "category": task.category,
            "correct": True,
            "repeated_reads": 0,
            "memory_hits": 1 if (config.use_memory and task.setup_turns) else (-1 if not task.setup_turns else 0),
            "read_target_after_setup": False,
            "tool_calls": 2,
            "duration": 0.5,
        }

    def _build_default_script(
        self,
        task: MemoryTask,
        workspace_root: str,
        use_memory: bool = True,
    ) -> list[list[dict[str, Any]]]:
        """为 ScriptedModelClient 构建默认行为脚本。

        策略：
        - 有 setup_turns 的任务：如果 use_memory=True，跳过 reread（用记忆回答）；
          如果 use_memory=False，reread 目标文件（需要重新获取信息）。
        - 无 setup_turns 的任务：始终读取第一个 target_file。

        这让 memory_on 和 memory_off 在 tool_calls / memory_hit 上产生差异。

        Args:
            task: 任务定义
            workspace_root: 工作区根目录
            use_memory: 是否启用记忆（影响脚本行为）

        Returns:
            轮次列表，每轮是 content_blocks 列表
        """
        rounds: list[list[dict[str, Any]]] = []

        # 判断是否应该跳过 reread（memory 生效时）
        should_skip_reread = use_memory and task.setup_turns

        if task.target_files and not should_skip_reread:
            # 读取第一个目标文件（memory_off 或无 setup_turns）
            target = task.target_files[0]
            file_path = str(Path(workspace_root) / target)
            rounds.append([
                {
                    "type": "tool_use",
                    "id": "call_read_1",
                    "name": "read",
                    "input": {"file_path": file_path},
                }
            ])

        # 最终回复
        if task.expected_substrings:
            default_answer = " ".join(task.expected_substrings[:3])
        else:
            default_answer = "Task completed based on file analysis."

        rounds.append([{"type": "text", "text": default_answer}])

        return rounds

    def _run_scripted_task(
        self,
        config: MemoryConfig,
        task: MemoryTask,
        reflection_config: ReflectionConfig | None = None,
    ) -> dict[str, Any]:
        """用 ScriptedModelClient + 真实 AgentLoop 运行任务。

        替代原来的 _run_mock_task() 常量返回路径。
        真实执行 tool（file_read 等），真实测量 tool_calls / duration。

        设计要点：
        - setup_turns 用独立的 FakeModelClient（简单文本回复，不消耗 script rounds）
        - 主任务用 ScriptedModelClient（按 script 执行 tool calls）
        - 两个 phase 的 client 分开，避免 setup 消耗主任务的 script rounds
        - 如果 reflection_config 启用且 task 有 retry_script，支持 one-shot reflection retry
        """
        from agent.evaluation.fake_client import FakeModelClient, ScriptedModelClient

        start_time = time.time()
        workspace_root = self._prepare_workspace(task)

        try:
            # --- Phase 1: setup_turns 用独立 FakeModelClient ---
            if task.setup_turns:
                setup_client = FakeModelClient(
                    ["OK, noted."] * len(task.setup_turns)
                )
                setup_loop = _create_agent_loop_with_client(
                    client=setup_client,
                    memory_enabled=config.use_memory,
                    workspace_root=workspace_root,
                    max_turns=self._max_turns,
                )

                # 注入无关记忆（只在 setup 阶段注入一次）
                if config.use_irrelevant_memory:
                    setup_loop.memory.set_task("这是一个无关的任务：处理用户登录页面的 CSS 样式")
                    for i in range(5):
                        setup_loop.memory.append_note(
                            f"无关笔记 {i}: 用户要求修改按钮颜色为蓝色",
                            tags=["noise"],
                        )

                for setup_prompt in task.setup_turns:
                    setup_loop.run(setup_prompt)

                # 把 setup 阶段的 memory 状态转移到主任务 loop
                # （因为 memory 是 per-loop 的，需要手动同步）
                memory_state = None
                if config.use_memory:
                    memory_state = {
                        "notes": list(setup_loop.memory._episodic._notes)
                            if hasattr(setup_loop.memory, '_episodic') else [],
                        "task": setup_loop.memory._task
                            if hasattr(setup_loop.memory, '_task') else "",
                    }

            # --- Phase 2: 主任务用 ScriptedModelClient ---
            script = self._build_default_script(
                task, workspace_root, use_memory=config.use_memory,
            )
            main_client = ScriptedModelClient(script)

            main_loop = _create_agent_loop_with_client(
                client=main_client,
                memory_enabled=config.use_memory,
                workspace_root=workspace_root,
                max_turns=self._max_turns,
            )

            # 注入无关记忆（如果 setup 阶段没有注入）
            if config.use_irrelevant_memory and not task.setup_turns:
                main_loop.memory.set_task("这是一个无关的任务：处理用户登录页面的 CSS 样式")
                for i in range(5):
                    main_loop.memory.append_note(
                        f"无关笔记 {i}: 用户要求修改按钮颜色为蓝色",
                        tags=["noise"],
                    )

            # 同步 memory 状态
            if config.use_memory and task.setup_turns and memory_state:
                main_loop.memory._task = memory_state["task"]
                if hasattr(main_loop.memory, '_episodic') and memory_state["notes"]:
                    main_loop.memory._episodic._notes = memory_state["notes"]

            # 跑主任务
            result_text = main_loop.run(task.prompt)

            # 从 tool_history 统计
            tool_calls = len(main_loop.tool_history)
            repeated_reads = _count_repeated_reads(
                main_loop.tool_history, task.target_files, workspace_root,
            )
            memory_hits = _compute_memory_hit(
                task, main_loop.tool_history, workspace_root,
            )
            read_target_after_setup = _check_target_reread(
                task, main_loop.tool_history, workspace_root,
            )
            correct = _verify_task_result(
                task, result_text, workspace_root, main_loop.tool_history,
            )

            duration = time.time() - start_time

            # 构建 first attempt 结果
            first_result = {
                "task_id": task.task_id,
                "category": task.category,
                "correct": correct,
                "repeated_reads": repeated_reads,
                "memory_hits": memory_hits,
                "read_target_after_setup": read_target_after_setup,
                "tool_calls": tool_calls,
                "duration": duration,
                "result_preview": result_text[:200] if result_text else "",
                "failed_reason": "",
                "is_abnormal": False,
                "abnormal_reason": "",
            }

            # --- Phase 3: Reflection Retry（如果启用且有 retry_script 或 retry_branches）---
            has_retry = task.retry_script is not None or task.retry_branches is not None
            if reflection_config and reflection_config.enabled and has_retry:
                from agent.reflection.policy import ReflectionPolicy
                from agent.reflection.builder import ReflectionBuilder
                from agent.reflection.types import ReflectionSummary

                policy = ReflectionPolicy(reflection_config)
                decision = policy.should_reflect(task, first_result)

                if decision.should_reflect:
                    # 构造 ReflectionPlan（结构化输出）
                    summary = ReflectionSummary(
                        task_id=task.task_id,
                        original_prompt=task.prompt,
                        first_attempt_correct=correct,
                        first_attempt_answer_preview=result_text[:200] if result_text else "",
                        tool_calls=tool_calls,
                        read_target_after_setup=read_target_after_setup,
                        memory_hit=memory_hits,
                        failure_reason=decision.reason,
                    )
                    builder = ReflectionBuilder(reflection_config)
                    plan = builder.build(summary)

                    # 选择 retry client：
                    # 有 retry_branches → PromptAwareScriptedModelClient（根据 plan.retry_strategy 选 branch）
                    # 只有 retry_script → ScriptedModelClient（固定 script）
                    if task.retry_branches:
                        from agent.evaluation.fake_client import PromptAwareScriptedModelClient
                        retry_client = PromptAwareScriptedModelClient(
                            branches=task.retry_branches,
                            default_branch=task.default_retry_branch,
                        )
                    else:
                        retry_client = ScriptedModelClient(task.retry_script)
                    retry_loop = _create_agent_loop_with_client(
                        client=retry_client,
                        memory_enabled=config.use_memory,
                        workspace_root=workspace_root,
                        max_turns=self._max_turns,
                    )

                    # 同步 memory 状态
                    if config.use_memory and task.setup_turns and memory_state:
                        retry_loop.memory._task = memory_state["task"]
                        if hasattr(retry_loop.memory, '_episodic') and memory_state["notes"]:
                            retry_loop.memory._episodic._notes = memory_state["notes"]

                    retry_text = retry_loop.run(plan.prompt)
                    retry_tool_calls = len(retry_loop.tool_history)
                    retry_correct = _verify_task_result(
                        task, retry_text, workspace_root, retry_loop.tool_history,
                    )
                    retry_reread = _check_target_reread(
                        task, retry_loop.tool_history, workspace_root,
                    )

                    # 返回 retry 结果，附带 reflection 元数据
                    duration = time.time() - start_time
                    return {
                        "task_id": task.task_id,
                        "category": task.category,
                        "correct": retry_correct,
                        "repeated_reads": _count_repeated_reads(
                            retry_loop.tool_history, task.target_files, workspace_root,
                        ),
                        "memory_hits": _compute_memory_hit(
                            task, retry_loop.tool_history, workspace_root,
                        ),
                        "read_target_after_setup": retry_reread,
                        "tool_calls": tool_calls + retry_tool_calls,
                        "duration": duration,
                        "result_preview": retry_text[:200] if retry_text else "",
                        "failed_reason": "",
                        "is_abnormal": False,
                        "abnormal_reason": "",
                        # reflection 元数据
                        "reflection_triggered": True,
                        "reflection_reason": decision.reason,
                        "reflection_trigger_type": decision.trigger_type,
                        "first_attempt_correct": correct,
                        "first_attempt_tool_calls": tool_calls,
                        "first_attempt_read_target": read_target_after_setup,
                    }

            # 无 reflection 或不触发
            first_result["reflection_triggered"] = False
            first_result["reflection_reason"] = ""
            first_result["reflection_trigger_type"] = "none"
            first_result["first_attempt_correct"] = correct
            first_result["first_attempt_tool_calls"] = tool_calls
            return first_result

        except Exception as e:
            duration = time.time() - start_time
            logger.error("Scripted task %s failed: %s", task.task_id, e)
            return {
                "task_id": task.task_id,
                "category": task.category,
                "correct": False,
                "repeated_reads": 0,
                "memory_hits": -1,
                "read_target_after_setup": False,
                "tool_calls": 0,
                "duration": duration,
                "result_preview": "",
                "failed_reason": "scripted_error",
                "is_abnormal": False,
                "abnormal_reason": str(e),
            }

    def _run_real_task(
        self,
        config: MemoryConfig,
        task: MemoryTask,
    ) -> dict[str, Any]:
        """使用真实模型运行任务（含 429 重试）"""
        start_time = time.time()
        max_retries = 3

        for attempt in range(max_retries):
            try:
                return self._run_real_task_inner(config, task, start_time)
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    wait = 5 * (2 ** attempt)
                    logger.warning("429 rate limited, retrying in %ds (attempt %d/%d)", wait, attempt + 1, max_retries)
                    time.sleep(wait)
                else:
                    # 判断异常类型
                    error_str = str(e).lower()
                    if "429" in error_str:
                        failed_reason = "api_429"
                        abnormal_reason = "API 429 rate limited"
                    elif "network" in error_str or "connection" in error_str or "timeout" in error_str:
                        failed_reason = "network_error"
                        abnormal_reason = "Network/connection error"
                    elif "500" in error_str or "502" in error_str or "503" in error_str:
                        failed_reason = "service_error"
                        abnormal_reason = "API service error (5xx)"
                    else:
                        failed_reason = "model_error"
                        abnormal_reason = ""

                    logger.error("Task %s failed (%s): %s", task.task_id, failed_reason, e)
                    return {
                        "task_id": task.task_id,
                        "category": task.category,
                        "correct": False,
                        "repeated_reads": 0,
                        "memory_hits": -1,
                        "read_target_after_setup": False,
                        "tool_calls": 0,
                        "duration": time.time() - start_time,
                        "result_preview": "",
                        "failed_reason": failed_reason,
                        "is_abnormal": failed_reason != "model_error",
                        "abnormal_reason": abnormal_reason,
                    }
        # unreachable
        return {}  # type: ignore[return-value]

    def _run_real_task_inner(
        self,
        config: MemoryConfig,
        task: MemoryTask,
        start_time: float,
    ) -> dict[str, Any]:
        """单次任务执行（不含重试）"""
        # 准备工作区
        workspace_root = self._prepare_workspace(task)

        try:
            loop = _create_real_agent_loop(
                memory_enabled=config.use_memory,
                workspace_root=workspace_root,
                max_turns=self._max_turns,
            )

            # 注入无关记忆（memory_enabled 必须为 True，否则噪声不会进 prompt）
            if config.use_irrelevant_memory:
                loop.memory.set_task("这是一个无关的任务：处理用户登录页面的 CSS 样式")
                for i in range(5):
                    loop.memory.append_note(
                        f"无关笔记 {i}: 用户要求修改按钮颜色为蓝色",
                        tags=["noise"],
                    )

            # 跑 setup_turns（前置对话）
            for setup_prompt in task.setup_turns:
                loop.run(setup_prompt)

            # 清空 tool_history，确保主阶段统计不被 setup_turns 污染
            loop.clear_tool_history()

            # 跑主任务
            result_text = loop.run(task.prompt)

            # 从 tool_history 统计
            tool_calls = len(loop.tool_history)
            repeated_reads = _count_repeated_reads(
                loop.tool_history, task.target_files, workspace_root,
            )
            memory_hits = _compute_memory_hit(
                task, loop.tool_history, workspace_root,
            )
            read_target_after_setup = _check_target_reread(
                task, loop.tool_history, workspace_root,
            )
            correct = _verify_task_result(task, result_text, workspace_root, loop.tool_history)

            # 记录 ContextMetadata 用于诊断
            if loop._last_context_metadata:
                meta = loop._last_context_metadata
                logger.info(
                    "  [%s] tokens: total_raw=%d, total_rendered=%d, truncated=%s",
                    task.task_id, meta.total_raw_tokens,
                    meta.total_rendered_tokens, meta.was_truncated,
                )
                for name, sec in meta.sections.items():
                    logger.info(
                        "    %s: raw=%d, rendered=%d, truncated=%s",
                        name, sec.raw_tokens, sec.rendered_tokens, sec.was_truncated,
                    )

        except Exception as e:
            # 判断异常类型
            error_str = str(e).lower()
            if "429" in error_str:
                failed_reason = "api_429"
                abnormal_reason = "API 429 rate limited"
            elif "network" in error_str or "connection" in error_str or "timeout" in error_str:
                failed_reason = "network_error"
                abnormal_reason = "Network/connection error"
            elif "500" in error_str or "502" in error_str or "503" in error_str:
                failed_reason = "service_error"
                abnormal_reason = "API service error (5xx)"
            else:
                failed_reason = "model_error"
                abnormal_reason = ""

            logger.error("Task %s failed (%s): %s", task.task_id, failed_reason, e)
            correct = False
            repeated_reads = 0
            memory_hits = -1
            tool_calls = 0
            result_text = ""

        duration = time.time() - start_time

        # 构建返回结果，包含异常标记
        result = {
            "task_id": task.task_id,
            "category": task.category,
            "correct": correct,
            "repeated_reads": repeated_reads,
            "memory_hits": memory_hits,
            "read_target_after_setup": read_target_after_setup,
            "tool_calls": tool_calls,
            "duration": duration,
            "result_preview": result_text[:200] if result_text else "",
        }

        # 如果是异常任务，添加异常标记
        if not correct and failed_reason:
            result["failed_reason"] = failed_reason
            result["is_abnormal"] = failed_reason != "model_error"
            result["abnormal_reason"] = abnormal_reason
        else:
            result["failed_reason"] = ""
            result["is_abnormal"] = False
            result["abnormal_reason"] = ""

        return result

    def _prepare_workspace(self, task: MemoryTask) -> str:
        """准备工作区（复制 fixture 文件到临时目录）

        Args:
            task: 任务定义

        Returns:
            工作区根目录路径
        """
        if not task.fixture_dir:
            # 无 fixture，使用 repo 根目录
            return str(Path.cwd())

        # 复制 fixture 到临时目录
        import tempfile
        tmp_dir = Path(tempfile.mkdtemp(prefix="memory_experiment_"))
        fixture_src = _FIXTURE_BASE / task.fixture_dir
        if fixture_src.exists():
            for f in fixture_src.iterdir():
                if f.is_file():
                    shutil.copy2(f, tmp_dir / f.name)
        return str(tmp_dir)

    # ============================================================
    # 报告生成
    # ============================================================

    def generate_report(self, results: list[MemoryAblationResult]) -> str:
        """生成实验报告"""
        report = []
        report.append("# Memory Experiment Report")
        report.append("")
        report.append("## 实验设计")
        report.append("")
        report.append("- memory_on: memory_enabled=True（完整记忆系统）")
        report.append("- memory_off: memory_enabled=False（真关闭，配置级）")
        report.append("- memory_irrelevant: memory_enabled=True + 注入噪声记忆")
        report.append("")

        # 任务分级统计
        report.append("## 任务分级统计")
        report.append("")
        report.append("| 等级 | 数量 | 说明 |")
        report.append("|------|------|------|")
        level_counts: dict[str, int] = {}
        for task in MEMORY_TASKS:
            level_counts[task.dependency_level] = level_counts.get(task.dependency_level, 0) + 1
        level_desc = {
            "L1": "不需要记忆也能答对",
            "L2": "记忆有帮助但不是必须",
            "L3": "记忆显著提升效率",
            "L4": "没有记忆几乎不可能答对",
        }
        for level in ["L1", "L2", "L3", "L4"]:
            if level in level_counts:
                report.append(f"| {level} | {level_counts[level]} | {level_desc.get(level, '')} |")
        report.append("")

        report.append("## 测试场景")
        report.append("")
        report.append("| 类别 | 数量 | 说明 |")
        report.append("|------|------|------|")
        categories: dict[str, int] = {}
        for task in MEMORY_TASKS:
            categories[task.category] = categories.get(task.category, 0) + 1
        cat_desc = {
            "fact_lookup": "问答类，验证 contains_text",
            "history_reference": "有 setup_turns，验证 memory_hit",
            "edit_dependency": "fixture 文件，验证 file_changed",
            "cross_round_recall": "跨轮事实回忆，验证 memory_hit",
            "cross_file_dep": "跨文件依赖修改，验证 file_changed",
            "multi_round_edit": "多轮连续改动，验证 multi_file_changed",
            "noise": "噪声干扰与错误纠偏，验证抗混淆能力",
            "memory_sensitive": "memory 敏感任务，memory_on 跳过 reread，memory_off 必须 reread",
        }
        for cat, count in categories.items():
            report.append(f"| {cat} | {count} | {cat_desc.get(cat, '')} |")
        report.append("")

        report.append("## 指标定义")
        report.append("")
        report.append("| 指标 | 定义 | 用途 |")
        report.append("|------|------|------|")
        report.append("| correct_rate | verifier 判定正确的任务比例 | 整体指标 |")
        report.append("| memory_dependent_success_rate | L3/L4 任务的正确率 | **主效果指标** |")
        report.append("| target_reread_rate | 主任务阶段重读目标文件的比例 | 效率指标 |")
        report.append("| answer_without_reread_rate | setup_turns 后不重读就能答对的比例 | 效率指标 |")
        report.append("| repeated_reads | 同一文件第 2 次及以后成功读取的总次数 | 诊断指标 |")
        report.append("| memory_hit_rate | 有 setup_turns 的任务中，主阶段未 reread 目标文件的比例 | 诊断指标（不作为主效果） |")
        report.append("| avg_tool_calls | 平均每任务工具调用次数 | 效率指标 |")
        report.append("| avg_duration | 平均每任务耗时（秒） | 效率指标 |")
        report.append("")

        report.append("## 实验结果")
        report.append("")
        report.append("| 配置 | correct_rate | memory_dependent_success_rate | target_reread_rate | answer_without_reread_rate | avg_tool_calls | avg_duration | 异常状态 |")
        report.append("|------|-------------|------------------------------|-------------------|---------------------------|---------------|-------------|----------|")
        for r in results:
            m = r.metrics
            abnormal_flag = f"⚠️ {r.abnormal_count} 个异常任务" if r.is_abnormal else "✅ 正常"
            report.append(
                f"| {r.config.name} | {m.correct_rate:.0%} | {m.memory_dependent_success_rate:.0%} ({m.l3l4_correct}/{m.l3l4_tasks}) | "
                f"{m.target_reread_rate:.0%} | {m.answer_without_reread_rate:.0%} | "
                f"{m.avg_tool_calls:.1f} | {m.avg_duration:.1f}s | {abnormal_flag} |"
            )
        report.append("")

        # 正式结论章节（只看 clean rounds）
        clean_results = [r for r in results if not r.is_abnormal]
        if clean_results:
            report.append("## 正式结论（只看 clean rounds）")
            report.append("")
            report.append("**以下结论只基于无异常任务的轮次：**")
            report.append("")
            for r in clean_results:
                m = r.metrics
                report.append(f"### {r.config.name}")
                report.append(f"- correct_rate: {m.correct_rate:.0%}")
                report.append(f"- **memory_dependent_success_rate: {m.memory_dependent_success_rate:.0%}**（L3/L4 任务 {m.l3l4_correct}/{m.l3l4_tasks}）")
                report.append(f"- target_reread_rate: {m.target_reread_rate:.0%}")
                report.append(f"- answer_without_reread_rate: {m.answer_without_reread_rate:.0%}")
                report.append("")
        else:
            report.append("## ⚠️ 无 clean rounds")
            report.append("")
            report.append("**所有轮次都存在异常任务，无法得出正式结论。**")
            report.append("")

        # 异常任务汇总
        abnormal_configs = [r for r in results if r.is_abnormal]
        if abnormal_configs:
            report.append("## ⚠️ 异常任务汇总")
            report.append("")
            report.append("以下 config 存在异常任务，不纳入正式统计：")
            report.append("")
            for r in abnormal_configs:
                report.append(f"### {r.config.name}（{r.abnormal_count} 个异常任务）")
                report.append("")
                report.append("| task_id | failed_reason | abnormal_reason |")
                report.append("|---------|---------------|-----------------|")
                for tr in r.task_results:
                    if tr.get("is_abnormal", False):
                        report.append(
                            f"| {tr['task_id']} | {tr.get('failed_reason', '')} | {tr.get('abnormal_reason', '')} |"
                        )
                report.append("")

        # 按 L1-L4 分组的任务详情
        report.append("## 各任务详情（按 L1-L4 分组）")
        report.append("")
        for level in ["L4", "L3", "L2", "L1"]:
            level_tasks = [t for t in MEMORY_TASKS if t.dependency_level == level]
            if not level_tasks:
                continue
            report.append(f"### {level} 任务（{len(level_tasks)} 个）")
            report.append("")
            for r in results:
                abnormal_mark = " ⚠️" if r.is_abnormal else ""
                report.append(f"#### {r.config.name}{abnormal_mark}")
                report.append("")
                report.append("| task_id | category | correct | repeated_reads | memory_hit | tool_calls | duration | failed_reason |")
                report.append("|---------|----------|---------|----------------|------------|------------|----------|---------------|")
                for tr in r.task_results:
                    # 只显示当前 level 的任务
                    task_obj = next((t for t in MEMORY_TASKS if t.task_id == tr["task_id"]), None)
                    if not task_obj or task_obj.dependency_level != level:
                        continue
                    mh = tr.get("memory_hits", -1)
                    mh_str = str(mh) if mh >= 0 else "n/a"
                    failed = tr.get("failed_reason", "")
                    report.append(
                        f"| {tr['task_id']} | {tr.get('category', '')} | {'✅' if tr.get('correct') else '❌'} | "
                        f"{tr.get('repeated_reads', 0)} | {mh_str} | "
                        f"{tr.get('tool_calls', 0)} | {tr.get('duration', 0):.1f}s | {failed} |"
                    )
                report.append("")

        return "\n".join(report)

    def save_report(
        self,
        results: list[MemoryAblationResult],
        filename: str = "P2-memory-experiment.md",
    ) -> Path:
        """保存实验报告"""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        report_path = self._output_dir / filename
        report = self.generate_report(results)
        report_path.write_text(report, encoding="utf-8")
        logger.info("Report saved to: %s", report_path)
        return report_path


# ============================================================
# 便捷函数
# ============================================================


def run_memory_experiment(use_real_model: bool = False) -> list[MemoryAblationResult]:
    """运行记忆实验"""
    experiment = MemoryExperiment(use_real_model=use_real_model)
    results = experiment.run()
    experiment.save_report(results)
    return results


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run memory experiment")
    parser.add_argument("--real", action="store_true", help="Use real API")
    args = parser.parse_args()

    results = run_memory_experiment(use_real_model=args.real)

    print("\n" + "=" * 60)
    print("Memory Experiment Results")
    print("=" * 60)

    for r in results:
        m = r.metrics
        print(f"\n{r.config.name}:")
        print(f"  correct_rate: {m.correct_rate:.0%}")
        print(f"  repeated_reads: {m.repeated_reads}")
        print(f"  memory_hit_rate: {m.memory_hit_rate:.0%} ({m.eligible_memory_tasks} eligible)")
        print(f"  avg_tool_calls: {m.avg_tool_calls:.1f}")
        print(f"  avg_duration: {m.avg_duration:.1f}s")
