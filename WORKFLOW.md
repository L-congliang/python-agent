# 工作流执行模板

**每次开始功能前，必须读这个文件并按步骤执行。**

---

## 模式判断

根据任务大小选择模式：
- **快速模式**（5-15 分钟）：改配置、修 typo、调样式 → 直接改 → 验证
- **标准模式**（30 分钟-2 小时）：加小功能、修复杂 bug → 走完下面的步骤
- **完整模式**（半天-几天）：做新系统、大架构改动 → 走完所有阶段

**不确定用哪个模式？问用户。**

---

## 标准模式步骤

### 步骤 1: /ce-brainstorm
- **做什么**: 探索需求，通过对话澄清
- **输出**: `docs/brainstorms/YYYY-MM-DD-<topic>-requirements.md`
- **完成后**: 进入步骤 2

### 步骤 2: /ce-plan
- **输入**: 步骤 1 的输出文件
- **输出**: `docs/plans/YYYY-MM-DD-NNN-<type>-<name>-plan.md`
- **完成后**: 进入步骤 3

### 步骤 3: TDD 实现
- **输入**: 步骤 2 的输出文件
- **输出**: 代码 + 测试
- **完成后**: 进入步骤 4

### 步骤 4: /ce-code-review
- **输入**: 步骤 3 的代码
- **输出**: 审查报告
- **完成后**: 进入步骤 5

### 步骤 5: 更新文档
- 更新 `feature_list.json`（标记功能为 done）
- 更新 `claude-progress.md`（记录本次改动）
- 更新 `DEV_SYNC.md`（记录本次工作内容）
- git commit + push

---

## 完整模式步骤

在标准模式基础上，增加：

### 决策阶段（步骤 1 之前）
- /office-hours → /plan-ceo-review → /plan-eng-review

### 执行阶段（步骤 3 内部）
- /gsd-plan-phase → TDD → /gsd-execute-phase → verify

### 沉淀阶段（步骤 5 之后）
- /ce-compound → /opsx:archive

---

## 输出文件规范

| 类型 | 输出位置 | 命名格式 |
|------|----------|----------|
| brainstorm | `docs/brainstorms/` | `YYYY-MM-DD-<topic>-requirements.md` |
| plan | `docs/plans/` | `YYYY-MM-DD-NNN-<type>-<name>-plan.md` |
| spec | `openspec/specs/` | `FXX-<name>.md` |
| solution | `docs/solutions/` | `YYYY-MM-DD-<topic>-solution.md` |

**注意**: spec 文件必须放在 `openspec/specs/`，不是 `specs/`。

---

## 快速检查清单

开始功能前问自己：
- [ ] 读了这个 WORKFLOW.md 吗？
- [ ] 确定了用哪个模式吗？
- [ ] 知道输出文件放哪里吗？

完成后问自己：
- [ ] 所有步骤都走完了吗？
- [ ] 输出文件都创建了吗？
- [ ] feature_list.json 更新了吗？
- [ ] DEV_SYNC.md 更新了吗？
- [ ] git push 了吗？
