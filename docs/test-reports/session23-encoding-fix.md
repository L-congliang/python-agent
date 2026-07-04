# Session 23 测试报告

## 测试目标

验证 Windows subprocess 编码修复 + 记忆实验框架可用性

## 测试环境

- Python 3.11.9 (pyenv-win)
- Windows 11 (中文系统, GBK 默认编码)
- mimo-v2.5-pro 模型
- 2026-07-04

## 修复项

| 文件 | 修复内容 | 状态 |
|------|---------|------|
| bash.py | subprocess.run 加 encoding="utf-8" | ✅ |
| grep.py | 同上 | ✅ |
| subagent.py | 2 处 | ✅ |
| workspace.py | 2 处 | ✅ |
| evaluator.py | 1 处 | ✅ |
| model.py | 429 重试增强 | ✅ |

## 单元测试

- 747 passed, 3 skipped, 3 deselected
- 已知失败：test_check_freshness_modified（checkpoint freshness，无关）

## 记忆实验结果（三轮）

| 配置 | correct_rate | repeated_reads | memory_hit_rate | avg_tool_calls | avg_duration |
|------|-------------|----------------|-----------------|----------------|--------------|
| memory_on | 100% | 1.0 | 100% | 2.2 | 10.7s |
| memory_off | 100% | 0.7 | 100% | 2.0 | 10.5s |
| memory_irrelevant | 100% | 1.0 | 100% | 2.6 | 11.8s |

**结论：** 评测框架稳定可复现。当前任务集太简单，无法体现记忆差异。需升级任务集。
