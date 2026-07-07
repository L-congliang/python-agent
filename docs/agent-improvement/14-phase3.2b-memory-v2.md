# Phase 3.2B Memory v2 - Cross-Session Retrieval + Layered Memory

更新时间：2026-07-07

## 1. 阶段目标

把当前"已经有骨架"的 memory，升级成默认 loop 可用、跨 session 可检索、层次更清晰、能被 baseline 量化验证的 Memory v2。

## 2. 核心交付

### 已完成
- ✅ Memory 分层边界：user_preferences / project_facts / episodic_notes
- ✅ Cross-session retrieval：session_search.py
- ✅ 默认 loop 接入：SessionSearch 接进 MemoryManager.assemble_layered()
- ✅ /inspect 可见性：memory summary 包含在 inspect 输出中
- ✅ 测试覆盖：15 passed
- ✅ Baseline 前后对比：已运行

### 未完成
- ⚠️ Recall 和 observation budget 精确对齐：当前只返回 top_k
- ⚠️ 在 FakeModelClient 下未观察到 correct_rate 提升

## 3. Memory 分层

| 类型 | 说明 | 存储位置 | 备注 |
|------|------|----------|------|
| user_preferences | 用户偏好（回答风格、工作方式） | durable memory | 由 user-preferences topic 承载 |
| project_facts | 项目事实（约定、目录结构、设计决策） | durable memory | 由 project-conventions / key-decisions / dependency-facts 多个 topic 承载 |
| episodic_notes | 事件笔记（某次任务的结论、调试发现） | episodic notes | 独立存储 |
| working_memory | 当前任务的工作记忆 | working memory | 独立存储 |

**注意：project_facts 由多个 durable topics 承载，不是完全统一的数据模型。**

## 4. Cross-Session Retrieval

**session_search.py 功能：**
- 搜索历史 session 文件（.agent/sessions/*.json）
- 搜索 durable memory（.agent/memory/topics/*.md）
- 返回 top_k 最相关的结果
- 不使用向量数据库，只用关键词匹配

**默认 loop 接入：**
```python
# manager.py assemble_layered()
# 5. cross_session_recall（hit top 1-3，SessionSearch 命中后注入）
if query:
    recall_results = self._session_search.search(query, top_k=3)
    if recall_results:
        recall_str = self._renderer.render_cross_session_recall(recall_results)
        if recall_str:
            layers.append(recall_str)
            injection_stats["cross_session_recall"] = len(recall_results)
```

## 5. Baseline 前后对比

**已运行 baseline，结果如下：**

| 指标 | memory_on | memory_off | Delta | 说明 |
|------|-----------|------------|-------|------|
| correct_rate | 1.0 | 1.0 | 0.0 | FakeModelClient 下未观察到提升 |
| memory_hit_rate | 1.0 | 0.0 | +1.0 | 最明确的差异指标 |
| avg_tool_calls | 2.0 | 2.0 | 0.0 | FakeModelClient 下未观察到差异 |

**结论：**
- ✅ Memory v2 已进入默认 recall 链路
- ⚠️ 在 FakeModelClient 下尚未观察到 correct_rate 提升
- ✅ 当前最明确的差异指标是 memory_hit_rate（memory_on 1.0 vs memory_off 0.0）
- 后续需要更敏感的任务集或真实远程模型补充验证

## 6. 测试覆盖

**新增测试文件：**
- `tests/test_memory_cross_session.py`（15 passed）

**测试覆盖：**
- memory 分层边界
- session search 能找到相关 session note
- session search 能找到 durable project fact
- /inspect 能显示 memory summary
- baseline schema 一致性
- **loop 构建 prompt 时包含 cross-session recall**
- **cross-session recall 受 budget 控制**

## 7. 运行命令

```bash
# 运行测试
uv run pytest tests/test_memory_cross_session.py -q

# 运行 baseline
uv run python scripts/run_phase32_baseline.py

# 全量测试
uv run pytest tests -q
```

## 8. 后续使用

**Phase 3.2C（Reflection）可以：**
- 对比 memory_on vs memory_v2 + reflection
- 验证 reflection 是否提升了 memory_dependent_success_rate

**需要更敏感的任务集或真实远程模型补充验证：**
- 当前 FakeModelClient 是确定性的，correct_rate 都是 1.0
- 需要真实远程模型才能看到真正的 memory 效果差异
