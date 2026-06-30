## ADDED Requirements

### Requirement: Working Memory

系统 SHALL 维护 Working Memory，包含：task_summary（当前任务描述）、recent_files（最近访问文件列表，最多 8 个，LRU）。

#### Scenario: 设置任务摘要

- **WHEN** 调用 memory.set_task_summary("修复 bug")
- **THEN** task_summary = "修复 bug"

#### Scenario: 记录文件访问

- **WHEN** 依次访问 file_a、file_b、file_a
- **THEN** recent_files = [file_b, file_a]（file_a 最近访问，排最后）

#### Scenario: LRU 淘汰

- **WHEN** recent_files 已有 8 个文件，访问第 9 个文件
- **THEN** 最早访问的文件被移除，recent_files 保持 8 个

### Requirement: File Summaries

系统 SHALL 在文件读取后，保留 180 字符的摘要。下次需要该文件时，先检查摘要是否有效（freshness 校验），有效则直接使用摘要，无效则重新读取。

#### Scenario: 生成摘要

- **WHEN** 读取文件 src/main.py（内容 1000 字符）
- **THEN** 保留前 180 字符作为摘要

#### Scenario: freshness 校验通过

- **WHEN** 文件未修改，摘要的 freshness 与当前 hash 一致
- **THEN** 直接使用摘要，不重新读取

#### Scenario: freshness 校验失败

- **WHEN** 文件被修改，摘要的 freshness 与当前 hash 不一致
- **THEN** 标记摘要失效，下次读取时重新生成

### Requirement: Episodic Notes

系统 SHALL 支持存储带时间戳和标签的事件笔记。每条笔记包含：text（内容，最多 500 字符）、tags（标签列表）、created_at（时间戳）、source（来源）。

#### Scenario: 添加笔记

- **WHEN** 调用 memory.append_note("发现 bug 在 line 42", tags=["bug"])
- **THEN** 笔记被添加到 episodic_notes 列表

#### Scenario: 去重

- **WHEN** 添加与已有笔记 text 相同的笔记
- **THEN** 不重复添加

#### Scenario: 容量限制

- **WHEN** episodic_notes 已有 12 条，添加第 13 条
- **THEN** 最早的笔记被移除，保持 12 条

### Requirement: 记忆检索

系统 SHALL 支持基于关键词和标签的检索。检索逻辑：先看 tag 精确命中，再看关键词重叠，最后看新近度。返回最相关的 3 条笔记。

#### Scenario: 标签精确匹配

- **WHEN** 查询包含 tag "bug"
- **THEN** 带 tag "bug" 的笔记排在最前面

#### Scenario: 关键词匹配

- **WHEN** 查询 "main.py 修复"
- **THEN** 包含 "main.py" 或 "修复" 的笔记被召回

#### Scenario: 无匹配

- **WHEN** 查询与所有笔记都不匹配
- **THEN** 返回空列表

### Requirement: 记忆渲染

系统 SHALL 提供给模型看的紧凑"仪表盘"格式，包含：task、recent_files、file_summaries（仅有效的）、episodic_notes 数量、durable_topics。

#### Scenario: 渲染完整记忆

- **WHEN** 有任务摘要、3 个最近文件、2 个文件摘要
- **THEN** 输出包含 Memory: 段落，列出 task、recent_files、file_summaries

#### Scenario: 空记忆

- **WHEN** 所有记忆字段为空
- **THEN** 输出 Memory: 段落，各字段显示 "-"

### Requirement: Durable Memory

系统 SHALL 支持跨 session 的持久记忆，按 topic 分类（project-conventions、key-decisions、dependency-facts、user-preferences）。存储在 .agent/memory/ 目录。

#### Scenario: 晋升到持久记忆

- **WHEN** 调用 memory.promote_durable([("project-conventions", "使用 4 空格缩进")])
- **THEN** 笔记被写入 .agent/memory/topics/project-conventions.md

#### Scenario: 加载持久记忆

- **WHEN** 启动新 session
- **THEN** 从 .agent/memory/ 加载所有 topic 的笔记
