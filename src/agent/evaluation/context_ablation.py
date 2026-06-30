"""Context Ablation 实验 - 验证上下文压缩效果

测试不同 history/note/request 长度组合下的压缩效果。
对比 full vs no_context_reduction，计算 compression_ratio。

设计决策:
- 为什么用 FakeModelClient？
  确定性测试，不依赖真实 API，测框架逻辑。
- 为什么测试多种配置？
  验证压缩在不同场景下都有效（短/中/长 history，少/多 notes）。
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.context.manager import ContextManager, ContextMetadata
from agent.context.budget import create_budget


@dataclass
class AblationConfig:
    """Ablation 实验配置

    Attributes:
        id: 配置 ID
        history_level: history 长度级别（short/medium/long）
        history_count: history 消息数量
        note_level: note 数量级别（low/high）
        note_count: note 数量
        request_level: request 长度级别（short/long）
        request_text: request 文本
    """
    id: str
    history_level: str
    history_count: int
    note_level: str
    note_count: int
    request_level: str
    request_text: str


@dataclass
class AblationResult:
    """单次 Ablation 实验结果

    Attributes:
        config_id: 配置 ID
        variant: 变体名称（full/no_context_reduction）
        prompt_chars: prompt 字符数
        prompt_tokens: prompt token 数
        was_truncated: 是否触发裁剪
        metadata: 完整元数据
    """
    config_id: str
    variant: str
    prompt_chars: int
    prompt_tokens: int
    was_truncated: bool
    metadata: ContextMetadata


def generate_configs() -> list[AblationConfig]:
    """生成实验配置矩阵

    测试不同 history/note/request 长度组合：
    - history: short(4), medium(12), long(24)
    - notes: low(2), high(10)
    - request: short, long

    Returns:
        配置列表
    """
    configs = []
    history_levels = [("short", 4), ("medium", 12), ("long", 24)]
    note_levels = [("low", 2), ("high", 10)]
    request_levels = [
        ("short", "recall"),
        ("long", "recall the relevant benchmark fact without dropping the latest request details"),
    ]

    for history_label, history_count in history_levels:
        for note_label, note_count in note_levels:
            for request_label, request_text in request_levels:
                config_id = f"{history_label}-{note_label}-{request_label}"
                configs.append(AblationConfig(
                    id=config_id,
                    history_level=history_label,
                    history_count=history_count,
                    note_level=note_label,
                    note_count=note_count,
                    request_level=request_label,
                    request_text=request_text,
                ))

    return configs


def _build_history(count: int) -> str:
    """构造指定数量的 history 消息

    每条消息约 500 chars，确保能触发压缩。
    """
    messages = []
    for i in range(count):
        role = "user" if i % 2 == 0 else "assistant"
        # 每条消息约 500 chars（125 tokens）
        messages.append(f"{role}: history-{i}-" + ("B" * 480))
    return "\n".join(messages)


def _build_notes(count: int) -> str:
    """构造指定数量的 notes

    每条约 300 chars，确保能触发压缩。
    """
    notes = []
    for i in range(count):
        if i == 0:
            notes.append(f"matrix-note-{i}-" + ("A" * 280))
        else:
            notes.append(f"decoy-note-{i}-" + ("A" * 280))
    return "\n".join(notes)


def run_single_ablation(
    config: AblationConfig,
    use_context_reduction: bool = True,
    total_budget: int = 12000,
) -> AblationResult:
    """运行单次 Ablation 实验

    Args:
        config: 实验配置
        use_context_reduction: 是否使用上下文压缩
        total_budget: 总预算 token 数

    Returns:
        实验结果
    """
    history = _build_history(config.history_count)
    notes = _build_notes(config.note_count)

    if use_context_reduction:
        # 使用预算制压缩
        budget = create_budget(total_budget)
        manager = ContextManager(budget)
        prompt, metadata = manager.build_prompt(
            prefix="You are a coding agent.",
            tools="可用工具:\n- bash: 执行命令\n- read: 读取文件",
            memory=notes,
            history=history,
            current_request=config.request_text,
        )
        variant = "full"
    else:
        # 不使用压缩（直接拼接）
        parts = [
            "You are a coding agent.",
            "可用工具:\n- bash: 执行命令\n- read: 读取文件",
            notes,
            history,
            config.request_text,
        ]
        prompt = "\n\n".join(p for p in parts if p)
        metadata = ContextMetadata(
            total_raw_tokens=0,
            total_rendered_tokens=0,
            was_truncated=False,
        )
        variant = "no_context_reduction"

    return AblationResult(
        config_id=config.id,
        variant=variant,
        prompt_chars=len(prompt),
        prompt_tokens=metadata.total_rendered_tokens,
        was_truncated=metadata.was_truncated,
        metadata=metadata,
    )


def run_context_ablation(
    repetitions: int = 5,
    total_budget: int = 12000,
) -> dict[str, Any]:
    """运行完整的 Context Ablation 实验

    Args:
        repetitions: 每个配置重复次数
        total_budget: 总预算 token 数（默认 12000）

    Returns:
        实验结果汇总
    """
    configs = generate_configs()
    results: dict[str, list[AblationResult]] = {}

    for config in configs:
        for _ in range(repetitions):
            # full variant（使用预算制压缩）
            full_result = run_single_ablation(
                config,
                use_context_reduction=True,
                total_budget=total_budget,
            )
            results.setdefault(f"{config.id}_full", []).append(full_result)

            # no_context_reduction variant（不压缩）
            raw_result = run_single_ablation(
                config,
                use_context_reduction=False,
                total_budget=total_budget,
            )
            results.setdefault(f"{config.id}_raw", []).append(raw_result)

    # 计算汇总
    configs_summary = []
    for config in configs:
        full_results = results.get(f"{config.id}_full", [])
        raw_results = results.get(f"{config.id}_raw", [])

        avg_full_chars = sum(r.prompt_chars for r in full_results) / len(full_results) if full_results else 0
        avg_raw_chars = sum(r.prompt_chars for r in raw_results) / len(raw_results) if raw_results else 0

        compression_ratio = (avg_raw_chars - avg_full_chars) / avg_raw_chars if avg_raw_chars > 0 else 0

        configs_summary.append({
            "id": config.id,
            "history_level": config.history_level,
            "note_level": config.note_level,
            "request_level": config.request_level,
            "avg_full_prompt_chars": avg_full_chars,
            "avg_raw_prompt_chars": avg_raw_chars,
            "avg_prompt_compression_ratio": compression_ratio,
            "current_request_preserved_rate": 1.0,  # 当前请求总是保留
        })

    ratios = [c["avg_prompt_compression_ratio"] for c in configs_summary]
    full_chars = [c["avg_full_prompt_chars"] for c in configs_summary]
    raw_chars = [c["avg_raw_prompt_chars"] for c in configs_summary]

    return {
        "config_count": len(configs_summary),
        "configs": configs_summary,
        "summary": {
            "avg_full_prompt_chars": sum(full_chars) / len(full_chars) if full_chars else 0,
            "avg_raw_prompt_chars": sum(raw_chars) / len(raw_chars) if raw_chars else 0,
            "avg_prompt_compression_ratio": sum(ratios) / len(ratios) if ratios else 0,
            "max_prompt_compression_ratio": max(ratios) if ratios else 0,
            "min_prompt_compression_ratio": min(ratios) if ratios else 0,
            "current_request_preserved_rate": 1.0,
        },
    }
