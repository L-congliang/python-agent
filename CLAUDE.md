# CLAUDE.md

本项目模仿 Claude Code，构建一个终端里的 AI 编程助手。

## 工作流

**开始任何功能开发前，必须先读 `~/.claude/WORKFLOW.md`，按工作流执行。**

工作流定义了 5 个阶段：决策 → 规划 → 执行 → 检验 → 沉淀，每个阶段有对应的 skill 命令。

### 模式判断

根据任务大小选择模式：
- **快速模式**（5-15 分钟）：改配置、修 typo、调样式 → 直接改 → 验证
- **标准模式**（30 分钟-2 小时）：加小功能、修复杂 bug → brainstorm → plan → TDD → code-review
- **完整模式**（半天-几天）：做新系统、大架构改动 → 走完所有阶段

### 标准模式必须走完的流程

```
/ce-brainstorm → /ce-plan → TDD → /ce-code-review
```

**不允许跳过任何步骤。** 如果不确定用哪个模式，问用户。

### Skill 使用规则

| 阶段 | Skill | 做什么 | 输出位置 |
|------|-------|--------|----------|
| 规划 | `/ce-brainstorm` | 探索需求，通过对话澄清 | `docs/brainstorms/` |
| 规划 | `/ce-plan` | 创建实现计划 | `docs/plans/` |
| 执行 | TDD | 测试驱动开发 | 代码+测试 |
| 检验 | `/ce-code-review` | 结构化代码审查 | 审查报告 |
| 沉淀 | `/ce-compound` | 记录解决方案 | `docs/solutions/` |

### ⚠️ 执行检查点（硬性规则）

**收到功能开发任务后，必须执行以下步骤，不能跳过：**

1. **确认模式** — 告诉用户你判断的模式（快速/标准/完整）和理由，等用户确认后才能开始
2. **标准/完整模式** — 必须按顺序使用对应 skill，不能以"需求清楚"或"改动不大"为由跳过
3. **使用 skill 前** — 如果不确定某个 skill 做什么，先读它的 SKILL.md

**绝对禁止：** 自行判断模式就直接写代码。

**使用方式**：直接通过 `Skill` 工具调用，不需要读 SKILL.md 文件。skill 由插件系统注册，调用时自动加载。

**备查**：如果需要深入了解某个 skill 的完整定义，SKILL.md 位于各插件目录下：
- CE skills: `~/.claude/plugins/compound-engineering/**/skills/<skill-name>/SKILL.md`
- gstack skills: `~/.claude/plugins/gstack/<skill-name>/SKILL.md`

## 项目定位

**这是实习项目，不是 demo。** 代码质量要达到能拿出去面试讲解的水平。

- **目标**: 构建一个类 Claude Code 的 CLI Agent，用 mimo v2.5pro 模型
- **发布形态**: CLI 工具（终端交互）
- **用户**: 开发者（通过 pip install 使用）
- **差异化**: 开源、可学习、使用国产模型

## 技术栈

- **模型**: mimo v2.5pro（小米），通过 Anthropic 兼容 API 调用
- **API 地址**: `https://token-plan-cn.xiaomimimo.com/anthropic`
- **SDK**: `anthropic`（只用 mimo，不需要兼容其他模型）
- **终端 UI**: `rich`（渲染）+ `prompt_toolkit`（输入交互）
- **其他**: pydantic, jsonschema, pytest
- **Python**: 3.12+

## 项目结构

```
src/agent/
├── core/           # 核心模块（model.py 模型层, loop.py 主循环, types.py 类型）
├── tools/          # 工具系统（base.py 协议, registry.py 注册, 各工具实现）
├── permissions/    # 权限控制
├── context/        # 上下文管理
└── cli/            # 终端 UI（app.py）
```

## 验证命令

每次完成改动后，必须运行以下命令确认没有破坏：

```bash
# 同步依赖（自动创建虚拟环境）
uv sync

# 类型检查
uv run mypy src/ --strict

# 运行测试
uv run pytest tests/ -x -v

# 完整验证（全部通过才能提交）
uv run make check
```

**没有通过验证的代码不能提交。**

## 开发流程

```
1. 读 DEV_SYNC.md → 了解上次在哪个地点做了什么
2. 读 feature_list.json → 确认当前要做的功能
3. 读 specs/F0X-*.md → 理解该功能的详细需求、接口、验收标准
4. 读 claude-progress.md → 了解上次 session 做到哪了
5. 写代码
6. 运行验证命令（make check）
7. 验证失败 → 修复 → 回到第 6 步
8. 验证通过 → 更新 feature_list.json 和 claude-progress.md
9. 更新 DEV_SYNC.md（记录本次工作内容和地点）
10. git add → git commit（写清楚改了什么）→ git push
```

### Spec 文件

每个功能在 `specs/` 目录下有一个对应的 spec 文件，包含：
- **需求**：这个功能要做什么
- **接口**：输入输出类型、方法签名
- **场景**：需要覆盖的测试场景
- **验收标准**：怎么算完成

开始做某个功能前，必须先读对应的 spec 文件。没有 spec 的功能不能开始实现。

## 核心规则

### 一次只做一个功能

从 `feature_list.json` 中选一个未完成的功能，做完再做下一个。不允许同时开三个功能然后都做一半。

### 每次改动必须推送 Git

每完成一个功能、改进或修复：
1. `git add` 相关文件
2. `git commit` 写清楚改了什么
3. `git push` 推送到远程

不允许本地堆积多个未推送的提交。

### 完成标准（实习项目级别）

一个功能"完成"必须满足：
- 实现符合 spec 文件中的要求
- 代码写完且通过验证命令
- 有对应的测试，覆盖正常路径和错误路径
- 关键设计决策有注释说明"为什么这么做"
- 能向面试官讲清楚这个模块的设计思路和 tradeoff
- `feature_list.json` 中标记为 done
- `claude-progress.md` 中记录了本次改动

### 代码风格（实习项目级别）

- 类型注解：所有函数签名必须有完整类型注解
- 文档字符串：公开接口必须有 docstring，说明参数、返回值、异常
- 错误处理：不吞异常，错误信息要有上下文
- 测试：核心路径必须有测试，不只是 happy path
- 注释：非显而易见的代码要注释"为什么"，不只是"做什么"
- 简单优先：不为未来写代码，只解决当前问题

### 学习笔记

用户问的概念性问题和回答要记录到 `LEARNING_NOTES.md`，方便复习。格式：
- 简略记录问题和答案
- 包含代码示例和对比表格
- 按主题分章节组织

### Session 结束前

- 更新 `DEV_SYNC.md`（记录本次地点和工作内容）
- 更新 `claude-progress.md`
- 更新 `feature_list.json`
- 记录未完成的工作和阻塞点
- 确保 git 状态干净（全部已提交推送）
