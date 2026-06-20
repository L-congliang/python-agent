# F05: Bash 工具

> **参考**: Claude Code 的 BashTool 实现
> **前置依赖**: F03 Tool Protocol

## 设计目标

实现 Bash 工具，让 Agent 能够执行 shell 命令。

这是编程助手的核心能力：
- 运行脚本、测试、构建命令
- 查看系统信息（进程、环境变量、文件系统）
- 执行 Git 操作
- 安装依赖

## 与 Claude Code 的对齐点

| Claude Code | python-agent | 说明 |
|-------------|--------------|------|
| `BashTool` | `BashTool` | 工具实现 |
| `command` 参数 | `command` 参数 | 要执行的命令 |
| `timeout` 参数 | `timeout` 参数 | 超时时间（秒） |
| `workdir` 参数 | `workdir` 参数 | 工作目录 |
| `background` 参数 | 暂不实现 | 后续异步支持 |
| 命令白名单 | 暂不实现 | F09 权限系统做 |

## 文件结构

```
src/agent/tools/
├── base.py           # 已有（Tool Protocol）
├── registry.py       # 已有（ToolRegistry）
├── __init__.py       # 已有
└── bash.py           # 新增：BashTool 实现
```

### `bash.py` 内部结构

```
bash.py
├── MAX_OUTPUT_LINES = 2000     # 输出截断上限
├── _shell_cache                 # shell 检测结果缓存
├── _detect_shell()              # 检测可用 shell（带缓存）
├── _truncate_output()           # 截断长输出（保留尾部）
├── validate_bash_input()        # 输入校验
├── execute_bash()               # 核心执行逻辑
└── bash_tool                    # build_tool() 工厂调用
```

---

## 接口定义

### 1. BashTool（`tools/bash.py`）

```python
from agent.tools.base import Tool, build_tool, ToolImpl
from agent.core.types import ToolResult, ValidationResult
from agent.core.context import ToolUseContext


# 工具参数 Schema
BASH_PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "要执行的 shell 命令",
        },
        "timeout": {
            "type": "number",
            "description": "超时时间（秒），默认 30",
            "default": 30,
        },
        "workdir": {
            "type": "string",
            "description": "工作目录（绝对路径），默认使用 context.cwd",
        },
    },
    "required": ["command"],
}


def execute_bash(input: dict, context: ToolUseContext) -> ToolResult:
    """执行 bash 命令

    Args:
        input: {"command": "ls -la", "timeout": 30, "workdir": "/tmp"}
        context: 工具执行上下文

    Returns:
        ToolResult: 包含 stdout/stderr 的结果
    """
    ...


# 使用 build_tool 工厂函数创建
bash_tool = build_tool(
    name="bash",
    description="执行 shell 命令。用于运行脚本、测试、构建、Git 操作等。",
    parameters=BASH_PARAMETERS,
    execute_fn=execute_bash,
    is_read_only=lambda input: False,      # bash 可能修改文件系统
    is_concurrency_safe=lambda input: False, # bash 通常不安全并行
    is_destructive=lambda input: False,      # 默认非破坏性，具体看命令
    validate_input=validate_bash_input,
    get_summary=lambda input: f"Running: {input.get('command', '')[:50]}",
    get_user_facing_name=lambda input: "Bash",
    get_activity_description=lambda input: f"Running {input.get('command', '')[:30]}",
)
```

### 2. Shell 检测（`_detect_shell`）

```python
import shutil
import sys

_shell_cache: tuple[str, str] | None = None

def _detect_shell() -> tuple[str, str]:
    """检测可用 shell，返回 (executable, arg_prefix)

    优先级：
    1. Git Bash (bash.exe) — 开发者最熟悉的环境，命令和 Linux 一致
    2. cmd.exe (Windows fallback) — 保底可用
    3. /bin/sh (Linux/Mac) — 标准 POSIX shell

    结果缓存，整个进程生命周期只检测一次。

    为什么用列表参数而不是 shell=True？
    - shell=True 会让 subprocess 用系统默认 shell，我们想自己控制用哪个
    - 列表参数 [bash, -c, command] 更明确，避免双重 shell 解析
    """
    global _shell_cache
    if _shell_cache is not None:
        return _shell_cache

    # 优先找 bash（Git Bash 或系统自带）
    bash = shutil.which("bash")
    if bash:
        _shell_cache = (bash, "-c")
        return _shell_cache

    # Windows fallback: cmd.exe
    if sys.platform == "win32":
        _shell_cache = ("cmd.exe", "/c")
        return _shell_cache

    # Linux/Mac: /bin/sh
    _shell_cache = ("/bin/sh", "-c")
    return _shell_cache
```

### 3. 输出截断（`_truncate_output`）

```python
MAX_OUTPUT_LINES = 2000

def _truncate_output(output: str, max_lines: int = MAX_OUTPUT_LINES) -> str:
    """截断过长的输出，保留尾部

    为什么保留尾部而不是头部？
    - 大多数命令的有用信息在最后（测试结果、错误信息）
    - ls 的文件列表头部是 . 和 ..，尾部才是新增文件
    - git log 最新的提交在最前面（但输出是头部）

    特殊处理：
    - 行数 <= max_lines：不截断，原样返回
    - 行数 > max_lines：保留最后 max_lines 行，头部加截断提示
    """
    lines = output.split('\n')
    if len(lines) <= max_lines:
        return output

    truncated = lines[-max_lines:]
    header = f"... (truncated {len(lines) - max_lines} lines)\n"
    return header + '\n'.join(truncated)
```

### 4. 命令执行（`execute_bash`）

```python
def execute_bash(input: dict, context: ToolUseContext) -> ToolResult:
    """执行 bash 命令

    实现细节:
    1. 提取参数（command, timeout, workdir）
    2. 检查中断状态
    3. 检测 shell（_detect_shell，首次检测后续缓存）
    4. 使用 subprocess.run 执行命令（列表参数，非 shell=True）
    5. 捕获 stdout, stderr, returncode
    6. 截断过长 stdout（_truncate_output，保留尾部 2000 行）
    7. 格式化输出（包含退出码）
    8. 处理超时异常

    Args:
        input: {"command": "ls -la", "timeout": 30, "workdir": "/tmp"}
        context: 工具执行上下文

    Returns:
        ToolResult:
        - output: "stdout 内容\n\n[stderr]\nstderr 内容\n\n[exit code: 0]"
        - is_error: returncode != 0 或超时
    """
    command = input["command"]
    timeout = input.get("timeout", 30)
    workdir = input.get("workdir") or context.cwd

    # 检查中断
    if context.abort_controller.is_aborted:
        return ToolResult(output="命令执行被取消", is_error=True)

    # 检测 shell
    shell_exe, shell_arg = _detect_shell()

    # 确保 workdir 是绝对路径（context.cwd 可能是 "."）
    if workdir and not os.path.isabs(workdir):
        workdir = os.path.abspath(workdir)

    try:
        # 使用 subprocess.run 执行（列表参数，自己控制 shell）
        result = subprocess.run(
            [shell_exe, shell_arg, command],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )

        # 格式化输出
        output_parts = []
        if result.stdout:
            stdout = _truncate_output(result.stdout)
            output_parts.append(stdout)
        if result.stderr:
            output_parts.append(f"\n[stderr]\n{result.stderr}")
        output_parts.append(f"\n[exit code: {result.returncode}]")

        output = "".join(output_parts)
        is_error = result.returncode != 0

        return ToolResult(output=output, is_error=is_error)

    except subprocess.TimeoutExpired:
        return ToolResult(
            output=f"命令超时（超过 {timeout} 秒）",
            is_error=True,
        )
    except Exception as e:
        return ToolResult(
            output=f"命令执行失败: {str(e)}",
            is_error=True,
        )
```

### 5. 输入校验（`validate_bash_input`）

```python
def validate_bash_input(input: dict, context: ToolUseContext) -> ValidationResult:
    """校验 bash 命令输入

    校验规则:
    1. command 必须存在且非空
    2. timeout 必须是正数
    3. workdir 如果指定，必须是绝对路径

    Args:
        input: 工具输入
        context: 工具执行上下文

    Returns:
        ValidationResult
    """
    command = input.get("command")
    if not command or not isinstance(command, str) or not command.strip():
        return ValidationResult.failure("command 不能为空")

    timeout = input.get("timeout", 30)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return ValidationResult.failure("timeout 必须是正数")

    workdir = input.get("workdir")
    if workdir is not None:
        if not isinstance(workdir, str) or not os.path.isabs(workdir):
            return ValidationResult.failure("workdir 必须是绝对路径")

    return ValidationResult.success()
```

---

## 核心设计决策

### 1. 为什么用 `subprocess.run` 而不是 `os.system`？

| 方案 | 优点 | 缺点 |
|------|------|------|
| `os.system` | 简单 | 无法捕获输出、无法超时、安全风险 |
| `subprocess.run` | 可控、可超时、分离 stdout/stderr | 稍复杂 |
| `subprocess.Popen` | 最灵活 | 太复杂，我们不需要 |

选择 `subprocess.run`：足够简单，又能满足所有需求。

### 2. 为什么用列表参数 + shell 检测，而不是 `shell=True`？

```python
# 旧方案：shell=True
subprocess.run(command, shell=True)

# 新方案：列表参数 + 自己控制 shell
shell_exe, shell_arg = _detect_shell()
subprocess.run([shell_exe, shell_arg, command])
```

**为什么改？**
- 项目运行在 Windows 上，`shell=True` 默认用 cmd.exe
- AI 模型训练数据全是 Linux 命令（ls, cat, grep），cmd.exe 不认识
- Git Bash 能跑这些命令，所以优先检测 bash
- 列表参数避免双重 shell 解析，更可控

**Shell 检测优先级**：
1. Git Bash（`bash.exe`）— 开发者标配，命令跨平台一致
2. `cmd.exe`（Windows fallback）— 保底可用
3. `/bin/sh`（Linux/Mac）— 标准 POSIX shell

**风险**：
- 用列表参数仍有命令注入风险
- 但我们的使用场景是开发者主动使用，不是 Web 应用
- 后续 F09 会加命令白名单/黑名单

### 3. 输出格式设计

```
stdout 内容（可能被截断）

[stderr]
stderr 内容

[exit code: 0]
```

**为什么这样设计？**
- stdout 是主要输出，放在最前面
- stderr 用 `[stderr]` 标记，方便模型区分
- 退出码用 `[exit code: N]` 标记，非零表示错误
- 模型可以根据退出码判断命令是否成功

### 4. 输出截断（保留尾部）

```python
MAX_OUTPUT_LINES = 2000

def _truncate_output(output: str, max_lines: int = MAX_OUTPUT_LINES) -> str:
    lines = output.split('\n')
    if len(lines) <= max_lines:
        return output
    truncated = lines[-max_lines:]
    header = f"... (truncated {len(lines) - max_lines} lines)\n"
    return header + '\n'.join(truncated)
```

**为什么截断？**
- `cat` 一个大文件可能产生几万行输出，撑爆模型上下文
- 2000 行上限足够大多数场景

**为什么保留尾部？**
- 大多数命令的有用信息在最后（测试结果、错误信息）
- ls 的文件列表头部是 `.` 和 `..`，尾部才是新增文件
- 截断时加提示行，模型知道输出被截断了

**截断时机**：先捕获完整 stdout，再截断。stderr 通常很短，不截断。

### 5. 超时处理

```python
try:
    result = subprocess.run(..., timeout=timeout)
except subprocess.TimeoutExpired:
    return ToolResult(output="命令超时", is_error=True)
```

**为什么默认 30 秒？**
- 大多数命令（ls, cat, git）几秒内完成
- 30 秒足够覆盖大部分场景
- 如果需要更长，模型可以传 `timeout` 参数

---

## 测试场景

### 1. 基本命令执行

```python
def test_basic_command():
    """执行简单的 echo 命令"""
    tool = bash_tool
    result = tool.execute({"command": "echo hello"}, context)
    assert "hello" in result.output
    assert not result.is_error
    assert "[exit code: 0]" in result.output
```

### 2. 命令失败

```python
def test_command_failure():
    """执行失败的命令"""
    tool = bash_tool
    result = tool.execute({"command": "ls /nonexistent"}, context)
    assert result.is_error
    assert "[exit code:" in result.output
    assert "[exit code: 0]" not in result.output
```

### 3. stderr 捕获

```python
def test_stderr_capture():
    """命令输出到 stderr"""
    tool = bash_tool
    result = tool.execute({"command": "echo error >&2"}, context)
    assert "[stderr]" in result.output
    assert "error" in result.output
```

### 4. 超时处理

```python
def test_timeout():
    """命令超时"""
    tool = bash_tool
    result = tool.execute(
        {"command": "sleep 10", "timeout": 1},
        context,
    )
    assert result.is_error
    assert "超时" in result.output
```

### 5. 工作目录

```python
def test_workdir():
    """指定工作目录"""
    tool = bash_tool
    result = tool.execute(
        {"command": "pwd", "workdir": "/tmp"},
        context,
    )
    assert "/tmp" in result.output
```

### 6. 输入校验

```python
def test_validate_empty_command():
    """空命令校验"""
    tool = bash_tool
    result = tool.validate_input({"command": ""}, context)
    assert not result.is_valid

def test_validate_invalid_timeout():
    """无效超时校验"""
    tool = bash_tool
    result = tool.validate_input(
        {"command": "ls", "timeout": -1},
        context,
    )
    assert not result.is_valid
```

### 7. 中断支持

```python
def test_abort():
    """中断命令执行"""
    context.abort_controller.abort()
    tool = bash_tool
    result = tool.execute({"command": "echo hello"}, context)
    assert result.is_error
    assert "取消" in result.output
```

### 8. 工具属性

```python
def test_tool_properties():
    """工具属性正确"""
    tool = bash_tool
    assert tool.name == "bash"
    assert "shell" in tool.description.lower() or "命令" in tool.description
    assert "command" in tool.parameters["properties"]
    assert not tool.is_read_only({})
    assert not tool.is_concurrency_safe({})
```

### 9. 摘要和名称

```python
def test_summary():
    """摘要包含命令"""
    tool = bash_tool
    summary = tool.get_summary({"command": "ls -la"})
    assert "ls -la" in summary

def test_user_facing_name():
    """用户可见名称"""
    tool = bash_tool
    assert tool.get_user_facing_name({}) == "Bash"
```

### 10. 特殊字符处理

```python
def test_special_characters():
    """命令包含特殊字符"""
    tool = bash_tool
    result = tool.execute({"command": "echo 'hello world'"}, context)
    assert "hello world" in result.output
```

### 11. 输出截断

```python
def test_output_truncation():
    """输出超过 2000 行时截断"""
    # 生成一个产生大量输出的命令
    tool = bash_tool
    result = tool.execute(
        {"command": "for i in $(seq 1 3000); do echo line $i; done"},
        context,
    )
    assert "truncated" in result.output
    assert "line 3000" in result.output  # 尾部保留
    assert "line 1" not in result.output  # 头部被截断

def test_output_no_truncation():
    """输出未超过 2000 行时不截断"""
    tool = bash_tool
    result = tool.execute({"command": "echo hello"}, context)
    assert "truncated" not in result.output
    assert "hello" in result.output
```

### 12. Shell 检测

```python
def test_shell_detection():
    """检测到可用 shell"""
    from agent.tools.bash import _detect_shell
    shell_exe, shell_arg = _detect_shell()
    assert shell_exe  # 不为空
    assert shell_arg in ("-c", "/c")  # bash 用 -c，cmd 用 /c

def test_shell_detection_cache():
    """shell 检测结果被缓存"""
    from agent.tools.bash import _detect_shell
    result1 = _detect_shell()
    result2 = _detect_shell()
    assert result1 is result2  # 同一个对象（缓存命中）
```

---

## 依赖

```
F03 Tool Protocol（必须）
```

## 验收标准

- [ ] `bash.py` 文件在 `src/agent/tools/`
- [ ] `BASH_PARAMETERS` 定义正确的 JSON Schema
- [ ] `execute_bash()` 函数实现完整
  - [ ] 使用 `subprocess.run` 执行命令
  - [ ] 捕获 stdout 和 stderr
  - [ ] 处理超时异常
  - [ ] 格式化输出（含退出码）
  - [ ] 检查中断状态
- [ ] `validate_bash_input()` 函数实现完整
  - [ ] command 非空校验
  - [ ] timeout 正数校验
  - [ ] workdir 绝对路径校验
- [ ] `bash_tool` 使用 `build_tool()` 创建
- [ ] 工具属性正确：
  - [ ] `name` = "bash"
  - [ ] `is_read_only` = False
  - [ ] `is_concurrency_safe` = False
  - [ ] `get_summary` 返回命令摘要
- [ ] 测试覆盖所有场景（≥10 个测试）
- [ ] `make check` 通过

## 面试可能问的问题

```
Q: 为什么用 subprocess.run 而不是 os.system？
A: subprocess.run 可以：
   1. 分别捕获 stdout 和 stderr
   2. 设置超时（timeout 参数）
   3. 获取退出码（returncode）
   4. 支持列表参数，自己控制 shell
   os.system 只返回退出码，无法获取输出。

Q: shell=True 有安全风险，怎么处理？
A: 我们其实没用 shell=True，而是用列表参数 [bash, -c, command] 自己控制 shell。
   安全由两个层面保障：
   1. 使用场景：这是开发者主动使用的工具，不是 Web 应用
   2. 权限控制：F09 会实现命令白名单/黑名单

Q: 为什么要做 shell 检测？
A: 项目运行在 Windows 上，但 AI 模型训练数据全是 Linux 命令。
   直接用 cmd.exe 会大量报错。优先用 Git Bash 能解决这个问题。
   同时保留 cmd.exe fallback，确保没有 Git 也能基本工作。

Q: 为什么输出要截断？保留尾部？
A: cat 一个大文件可能产生几万行输出，撑爆模型上下文。
   保留尾部是因为大多数命令的有用信息在最后：
   - 测试结果在尾部
   - 错误信息在尾部
   - ls 新增文件在尾部

Q: 如何处理长时间运行的命令？
A: 三个机制：
   1. timeout 参数：默认 30 秒，超时自动终止
   2. AbortController：用户可以 Ctrl+C 中断
   3. 后续支持 background 模式（异步执行）

Q: 输出格式为什么这样设计？
A: 让模型能清晰区分：
   - stdout：命令的正常输出
   - stderr：错误信息（用 [stderr] 标记）
   - 退出码：命令是否成功（0 = 成功）
   模型可以根据这些信息决定下一步操作。

Q: 工作目录怎么处理？
A: subprocess.run 的 cwd 参数直接指定。
   校验时要求绝对路径，避免相对路径歧义。
   如果不指定，使用进程当前目录。
```
