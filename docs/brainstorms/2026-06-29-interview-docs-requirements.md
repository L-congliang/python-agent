---
date: "2026-06-29"
topic: interview-docs
---

## Summary

为 python-agent 项目构建面试准备文档体系：从代码中提取设计决策写成 ADR，整理结构化面试故事卡，补充 Skills/MCP 等技术的理解笔记，更新 resume-highlights.md 作为入口。目标是把"能跑的代码"变成"能讲清楚的项目"。

## Problem Frame

项目已有 11 个功能模块（F01-F11），代码中有大量设计决策注释（Protocol vs ABC、fail-closed 默认值、流式响应处理等），但这些内容散落在代码里，没有被系统性地整理。

现有 `docs/resume-highlights.md` 只更新到 F07，格式是"简历项目描述"而非"面试故事卡"，缺少设计决策的深度记录。

面试场景下，需要能回答三层问题：基础层（架构是什么）、技术深度层（为什么这么设计）、实战故事层（遇到过什么问题怎么解决的）。目前只有第一层有文档支撑。

## Requirements

**ADR 文档（设计决策记录）**

R1. 每个重大设计决策写一篇 ADR，包含：背景、考虑的方案、最终决策、原因、踩过的坑、替代方案。
R2. ADR 存放在 `docs/adr/` 目录，文件名格式 `NNN-<topic>.md`。
R3. 初始 ADR 覆盖 6 个已有决策：Tool Protocol 选型、Fail-closed 默认值、StreamResult 设计、Adapter 模式、ToolUseContext 信息隐藏、AbortController 协作取消。
R4. 每篇 ADR 控制在 1 页以内，重点是"为什么"而不是"做了什么"。

**面试故事卡**

R5. 每个故事采用结构化格式：一句话版本 → 问题描述 → 尝试过程 → 解决方案 → 学到的东西。
R6. 故事卡存放在 `docs/interview-stories/` 目录，文件名格式 `NNN-<topic>.md`。
R7. 初始故事卡覆盖 4 个经历：流式响应丢 tool_use、Windows 兼容性问题、编码检测策略、多模型适配。

**技术深度笔记**

R8. 记录尚未实现但需要理解的技术：Skills 系统、MCP 协议、工具调用错误处理、上下文管理策略。
R9. 笔记存放在 `docs/technical-deep-dive/` 目录。
R10. 每篇笔记包含：是什么、解决什么问题、如果我要做怎么设计、和现有架构的关系。
R11. 不要求实现，只要求理解到能讲清楚的程度。

**概览文档更新**

R12. 更新 `docs/resume-highlights.md` 到 F11，补充 F08-F11 的内容。
R13. 在概览中添加指向 ADR、故事卡、技术笔记的链接，作为入口文档。

**文档维护规则**

R14. 每次完成新功能后，同步更新相关 ADR、故事卡和概览文档。
R15. 将文档维护要求写入 `CLAUDE.md` 的开发流程中。

## Key Decisions

**文档拆分而非堆在一个文件里**
resume-highlights.md 保留为快速概览（面试前 5 分钟扫一眼），ADR 和故事卡作为深度参考（面试官追问时有内容可讲）。拆分后每个文档职责单一，更新也更方便。

**ADR 要包含踩坑和替代方案**
不只是记录"选了什么"，还要记录"试过什么不行"和"踩过什么坑"。这是面试中最有说服力的部分——展示了工程判断过程，而不是单纯的结果。

**技术笔记只写理解不写实现**
Skills、MCP 等技术不需要在这个项目中实现，但需要理解到能讲清楚"如果我要做，我会怎么做"的程度。这比盲目实现更有面试价值。

**执行分两批**
第一批：ADR + 故事卡 + 更新概览（已有素材，最快出成果）。第二批：技术笔记（需要研究未实现的技术）。

## Scope Boundaries

- 实现 Skills、MCP 等新功能（只记录理解，不写代码）
- 写技术博客（可以后续做，不在本次范围）
- 重构现有代码（只整理文档，不改代码）
- 自动生成文档（手动整理，保证质量）

## Acceptance Examples

**AE1. 面试官问"为什么用 Protocol 不用 ABC"**
打开 `docs/adr/001-tool-protocol.md`，能讲清楚：背景（需要统一工具接口）、考虑的方案（ABC / Protocol / dict）、选 Protocol 的原因（不需要继承、mock 方便）、踩过的坑（如果有）。

**AE2. 面试官问"你遇到过什么 bug"**
打开 `docs/interview-stories/01-stream-tool-use.md`，能讲清楚：问题（流式响应丢 tool_use）、尝试（只用 text_stream → 信息丢失）、解决（StreamResult 同时暴露迭代器和 blocks）、学到的（流式 API 的 text 和 structured data 是分开的）。

**AE3. 面试官问"MCP 协议你了解吗"**
打开 `docs/technical-deep-dive/mcp-protocol.md`，能讲清楚：MCP 是什么（Model Context Protocol）、解决什么问题（标准化工具调用接口）、和现有架构的关系（我们的 Tool Protocol 是简化版 MCP）。

## Outstanding Questions

- Deferred to Planning: ADR 的具体格式模板（标题、章节结构）
- Deferred to Planning: 故事卡的一句话版本怎么写最精炼
- Deferred to Planning: 技术笔记的深度标准（多详细算"能讲清楚"）
