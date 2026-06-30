## ADDED Requirements

### Requirement: Glob 模式匹配

系统 SHALL 支持标准 glob 模式匹配，包括：
- `*` 匹配任意字符（不含路径分隔符）
- `**` 递归匹配任意层级目录
- `?` 匹配单个字符
- `[abc]` 匹配括号内的字符

#### Scenario: 简单模式匹配
- **WHEN** 用户调用 `glob(pattern="*.py", path="src/agent")`
- **THEN** 返回 src/agent 目录下所有 .py 文件路径

#### Scenario: 递归模式匹配
- **WHEN** 用户调用 `glob(pattern="**/*.py")`
- **THEN** 返回当前工作目录下所有层级的 .py 文件路径

#### Scenario: 多层递归
- **WHEN** 用户调用 `glob(pattern="src/**/*.ts")`
- **THEN** 返回 src 目录下所有层级的 .ts 文件路径

### Requirement: 路径参数

系统 SHALL 支持可选的 path 参数，指定搜索目录。

#### Scenario: 指定绝对路径
- **WHEN** 用户调用 `glob(pattern="*.py", path="/absolute/path")`
- **THEN** 在 /absolute/path 目录下搜索

#### Scenario: 指定相对路径
- **WHEN** 用户调用 `glob(pattern="*.py", path="src")`
- **THEN** 在 cwd/src 目录下搜索

#### Scenario: 默认路径
- **WHEN** 用户调用 `glob(pattern="*.py")`（不指定 path）
- **THEN** 在当前工作目录（cwd）下搜索

### Requirement: 结果数量限制

系统 SHALL 支持 max_results 参数限制返回数量，默认 100。

#### Scenario: 默认限制
- **WHEN** 匹配结果超过 100 个文件
- **THEN** 只返回前 100 个，末尾显示 "(共 N 个文件，显示前 100 个)"

#### Scenario: 自定义限制
- **WHEN** 用户调用 `glob(pattern="**/*", max_results=50)`
- **THEN** 最多返回 50 个文件

#### Scenario: 结果不足限制
- **WHEN** 匹配结果只有 10 个文件，max_results=100
- **THEN** 返回全部 10 个文件，末尾显示 "(共 10 个文件)"

### Requirement: 排序选项

系统 SHALL 支持 sort_by 参数，默认按修改时间排序。

#### Scenario: 按修改时间排序（默认）
- **WHEN** 用户调用 `glob(pattern="*.py")`
- **THEN** 结果按文件修改时间降序排列（最新修改的在前）

#### Scenario: 按路径排序
- **WHEN** 用户调用 `glob(pattern="*.py", sort_by="path")`
- **THEN** 结果按文件路径字母顺序排列

### Requirement: 输入校验

系统 SHALL 校验输入参数的合法性。

#### Scenario: pattern 为空
- **WHEN** 用户调用 `glob(pattern="")`
- **THEN** 返回 ValidationResult.failure("pattern 不能为空")

#### Scenario: pattern 不是字符串
- **WHEN** 用户调用 `glob(pattern=123)`
- **THEN** 返回 ValidationResult.failure("pattern 必须是字符串")

#### Scenario: path 不存在
- **WHEN** 用户调用 `glob(pattern="*.py", path="/nonexistent")`
- **THEN** 返回 ValidationResult.failure("路径不存在: /nonexistent")

#### Scenario: max_results 非正整数
- **WHEN** 用户调用 `glob(pattern="*.py", max_results=0)`
- **THEN** 返回 ValidationResult.failure("max_results 必须是正整数")

### Requirement: 工具属性

Glob 工具 SHALL 具有以下属性：
- name: "glob"
- description: "按模式匹配查找文件"
- is_read_only: True
- is_concurrency_safe: True

#### Scenario: 只读属性
- **WHEN** 调用 `tool.is_read_only({})`
- **THEN** 返回 True

#### Scenario: 并发安全属性
- **WHEN** 调用 `tool.is_concurrency_safe({})`
- **THEN** 返回 True
