"""
F03 Tool Protocol 测试

测试覆盖:
1. PermissionDecision / ValidationResult 工厂方法
2. AbortController / FileReadState 行为
3. build_tool 默认值和覆盖
4. ToolRegistry 注册、查询、过滤
5. to_anthropic_tools 格式转换
6. validate_and_execute 完整流程（成功、失败、异常）
"""

import pytest

from agent.core.types import (
    PermissionBehavior, PermissionDecision,
    ValidationResult, ToolResult,
)
from agent.core.context import AbortController, FileReadState, ToolUseContext
from agent.tools.base import build_tool, Tool, ToolImpl
from agent.tools.registry import ToolRegistry


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_context() -> ToolUseContext:
    """测试用的 ToolUseContext"""
    return ToolUseContext(model="test-model")


@pytest.fixture
def simple_tool() -> ToolImpl:
    """最简单的工具：只有必填字段"""
    return build_tool(
        name="test",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        execute_fn=lambda input, ctx: ToolResult(output="ok"),
    )


@pytest.fixture
def registry_with_tools() -> ToolRegistry:
    """预装了几个工具的注册表"""
    reg = ToolRegistry()
    reg.register(build_tool(
        name="bash",
        description="Execute shell command",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
        execute_fn=lambda i, c: ToolResult(output=f"executed: {i.get('command')}"),
        is_read_only=lambda i: False,
    ))
    reg.register(build_tool(
        name="read_file",
        description="Read a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        execute_fn=lambda i, c: ToolResult(output="file content"),
        is_read_only=lambda i: True,
        is_concurrency_safe=lambda i: True,
    ))
    reg.register(build_tool(
        name="disabled_tool",
        description="A disabled tool",
        parameters={"type": "object", "properties": {}},
        execute_fn=lambda i, c: ToolResult(output="should not run"),
        is_enabled=lambda: False,
    ))
    return reg


# ============================================================
# 1. PermissionDecision 工厂方法
# ============================================================

class TestPermissionDecision:
    """PermissionDecision 工厂方法测试"""

    def test_allow(self):
        """allow() 创建 ALLOW 决策"""
        decision = PermissionDecision.allow()
        assert decision.behavior == PermissionBehavior.ALLOW
        assert decision.message == ""
        assert decision.updated_input is None

    def test_allow_with_updated_input(self):
        """allow() 可附带修改后的 input"""
        updated = {"command": "ls -la"}
        decision = PermissionDecision.allow(updated_input=updated)
        assert decision.behavior == PermissionBehavior.ALLOW
        assert decision.updated_input == updated

    def test_deny(self):
        """deny() 创建 DENY 决策"""
        decision = PermissionDecision.deny("没有权限")
        assert decision.behavior == PermissionBehavior.DENY
        assert decision.message == "没有权限"

    def test_ask(self):
        """ask() 创建 ASK 决策"""
        decision = PermissionDecision.ask("确认执行？")
        assert decision.behavior == PermissionBehavior.ASK
        assert decision.message == "确认执行？"


# ============================================================
# 2. ValidationResult 工厂方法
# ============================================================

class TestValidationResult:
    """ValidationResult 工厂方法测试"""

    def test_success(self):
        """success() 创建成功的校验结果"""
        result = ValidationResult.success()
        assert result.is_valid is True
        assert result.message == ""
        assert result.error_code == 0

    def test_failure(self):
        """failure() 创建失败的校验结果"""
        result = ValidationResult.failure("缺少参数", error_code=422)
        assert result.is_valid is False
        assert result.message == "缺少参数"
        assert result.error_code == 422


# ============================================================
# 3. AbortController
# ============================================================

class TestAbortController:
    """AbortController 测试"""

    def test_initial_state(self):
        """初始状态未中断"""
        controller = AbortController()
        assert controller.is_aborted is False

    def test_abort(self):
        """abort() 后状态变为已中断"""
        controller = AbortController()
        controller.abort()
        assert controller.is_aborted is True


# ============================================================
# 4. FileReadState
# ============================================================

class TestFileReadState:
    """FileReadState 测试"""

    def test_initial_empty(self):
        """初始状态为空"""
        state = FileReadState()
        assert state.get("any_path") is None
        assert state.has("any_path") is False

    def test_set_and_get(self):
        """set 后 get 能取到值"""
        state = FileReadState()
        state.set("src/main.py", "print('hello')")
        assert state.get("src/main.py") == "print('hello')"
        assert state.has("src/main.py") is True

    def test_different_paths(self):
        """不同路径互不影响"""
        state = FileReadState()
        state.set("a.py", "content_a")
        state.set("b.py", "content_b")
        assert state.get("a.py") == "content_a"
        assert state.get("b.py") == "content_b"


# ============================================================
# 5. build_tool 默认值
# ============================================================

class TestBuildToolDefaults:
    """build_tool 默认值测试"""

    def test_basic_properties(self, simple_tool):
        """基本属性正确"""
        assert simple_tool.name == "test"
        assert simple_tool.description == "A test tool"
        assert simple_tool.parameters == {"type": "object", "properties": {}}

    def test_is_enabled_default(self, simple_tool):
        """默认启用"""
        assert simple_tool.is_enabled() is True

    def test_is_concurrency_safe_default(self, simple_tool):
        """默认不安全（fail-closed）"""
        assert simple_tool.is_concurrency_safe({}) is False

    def test_is_read_only_default(self, simple_tool):
        """默认非只读（fail-closed）"""
        assert simple_tool.is_read_only({}) is False

    def test_is_destructive_default(self, simple_tool):
        """默认非破坏性"""
        assert simple_tool.is_destructive({}) is False

    def test_validate_input_default(self, simple_tool, mock_context):
        """默认校验通过"""
        result = simple_tool.validate_input({}, mock_context)
        assert result.is_valid is True

    def test_check_permissions_default(self, simple_tool, mock_context):
        """默认允许"""
        decision = simple_tool.check_permissions({}, mock_context)
        assert decision.behavior == PermissionBehavior.ALLOW

    def test_to_tool_result_block_default(self, simple_tool):
        """默认返回纯文本格式"""
        block = simple_tool.to_tool_result_block("output", "tool_123")
        assert block["tool_use_id"] == "tool_123"
        assert block["type"] == "tool_result"
        assert block["content"] == "output"

    def test_get_summary_default(self, simple_tool):
        """默认返回 None"""
        assert simple_tool.get_summary({}) is None

    def test_get_user_facing_name_default(self, simple_tool):
        """默认返回 name"""
        assert simple_tool.get_user_facing_name({}) == "test"

    def test_get_activity_description_default(self, simple_tool):
        """默认返回 None"""
        assert simple_tool.get_activity_description({}) is None

    def test_execute(self, simple_tool, mock_context):
        """执行函数正常工作"""
        result = simple_tool.execute({}, mock_context)
        assert result.output == "ok"
        assert result.is_error is False


# ============================================================
# 6. build_tool 覆盖
# ============================================================

class TestBuildToolOverrides:
    """build_tool 覆盖默认值测试"""

    def test_override_is_read_only(self):
        """覆盖 is_read_only"""
        tool = build_tool(
            name="read",
            description="Read file",
            parameters={},
            execute_fn=lambda i, c: ToolResult(output="content"),
            is_read_only=lambda i: True,
        )
        assert tool.is_read_only({}) is True

    def test_override_is_concurrency_safe(self):
        """覆盖 is_concurrency_safe"""
        tool = build_tool(
            name="safe",
            description="Safe tool",
            parameters={},
            execute_fn=lambda i, c: ToolResult(output="ok"),
            is_concurrency_safe=lambda i: True,
        )
        assert tool.is_concurrency_safe({}) is True

    def test_override_validate_input(self):
        """覆盖 validate_input"""
        tool = build_tool(
            name="validated",
            description="Validated tool",
            parameters={},
            execute_fn=lambda i, c: ToolResult(output="ok"),
            validate_input=lambda i, c: ValidationResult.failure("bad input"),
        )
        result = tool.validate_input({}, ToolUseContext(model="test"))
        assert result.is_valid is False
        assert result.message == "bad input"

    def test_override_check_permissions(self):
        """覆盖 check_permissions"""
        tool = build_tool(
            name="restricted",
            description="Restricted tool",
            parameters={},
            execute_fn=lambda i, c: ToolResult(output="ok"),
            check_permissions=lambda i, c: PermissionDecision.deny("no way"),
        )
        decision = tool.check_permissions({}, ToolUseContext(model="test"))
        assert decision.behavior == PermissionBehavior.DENY

    def test_empty_name_raises(self):
        """空名称抛出 ValueError"""
        with pytest.raises(ValueError, match="名称不能为空"):
            build_tool(
                name="",
                description="test",
                parameters={},
                execute_fn=lambda i, c: ToolResult(output="ok"),
            )


# ============================================================
# 7. Tool 协议检查
# ============================================================

class TestToolProtocol:
    """Tool 协议检查测试"""

    def test_tool_impl_is_tool(self, simple_tool):
        """ToolImpl 实现了 Tool 协议"""
        assert isinstance(simple_tool, Tool)

    def test_custom_class_is_tool(self):
        """自定义类只要结构匹配也算实现 Tool 协议"""

        class MyTool:
            @property
            def name(self) -> str:
                return "my_tool"

            @property
            def description(self) -> str:
                return "My tool"

            @property
            def parameters(self) -> dict:
                return {}

            def is_enabled(self) -> bool:
                return True

            def is_concurrency_safe(self, input: dict) -> bool:
                return False

            def is_read_only(self, input: dict) -> bool:
                return False

            def is_destructive(self, input: dict) -> bool:
                return False

            def check_permissions(self, input, context):
                return PermissionDecision.allow()

            def validate_input(self, input, context):
                return ValidationResult.success()

            def execute(self, input, context):
                return ToolResult(output="ok")

            def to_tool_result_block(self, output, tool_use_id):
                return {"tool_use_id": tool_use_id, "type": "tool_result", "content": str(output)}

            def get_summary(self, input):
                return None

            def get_user_facing_name(self, input):
                return "MyTool"

            def get_activity_description(self, input):
                return None

        tool = MyTool()
        assert isinstance(tool, Tool)


# ============================================================
# 8. ToolRegistry 注册和查询
# ============================================================

class TestToolRegistryRegister:
    """ToolRegistry 注册和查询测试"""

    def test_register_and_get(self, simple_tool):
        """注册工具后能按名称获取"""
        registry = ToolRegistry()
        registry.register(simple_tool)
        assert registry.get("test") is simple_tool

    def test_register_duplicate_raises(self, simple_tool):
        """重复注册同名工具抛出 ValueError"""
        registry = ToolRegistry()
        registry.register(simple_tool)
        with pytest.raises(ValueError, match="已注册"):
            registry.register(simple_tool)

    def test_unregister(self, simple_tool):
        """注销工具后无法获取"""
        registry = ToolRegistry()
        registry.register(simple_tool)
        registry.unregister("test")
        assert registry.get("test") is None

    def test_unregister_nonexistent_raises(self):
        """注销不存在的工具抛出 KeyError"""
        registry = ToolRegistry()
        with pytest.raises(KeyError, match="未注册"):
            registry.unregister("nonexistent")

    def test_get_nonexistent_returns_none(self):
        """获取不存在的工具返回 None"""
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_get_all(self, registry_with_tools):
        """get_all 返回所有工具"""
        tools = registry_with_tools.get_all()
        assert len(tools) == 3

    def test_get_enabled_tools(self, registry_with_tools):
        """get_enabled_tools 过滤掉禁用的工具"""
        tools = registry_with_tools.get_enabled_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "disabled_tool" not in names

    def test_register_non_tool_raises(self):
        """注册非 Tool 类型抛出 TypeError"""
        registry = ToolRegistry()
        with pytest.raises(TypeError, match="Tool 协议"):
            registry.register("not a tool")  # type: ignore


# ============================================================
# 9. to_anthropic_tools
# ============================================================

class TestToAnthropicTools:
    """to_anthropic_tools 格式转换测试"""

    def test_basic_conversion(self):
        """正确转换为 Anthropic API 格式"""
        registry = ToolRegistry()
        registry.register(build_tool(
            name="bash",
            description="Execute shell command",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            execute_fn=lambda i, c: ToolResult(output="ok"),
        ))
        tools = registry.to_anthropic_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "bash"
        assert tools[0]["description"] == "Execute shell command"
        assert "input_schema" in tools[0]
        assert tools[0]["input_schema"]["type"] == "object"

    def test_excludes_disabled(self, registry_with_tools):
        """禁用的工具不包含在 API 格式中"""
        tools = registry_with_tools.to_anthropic_tools()
        names = {t["name"] for t in tools}
        assert "disabled_tool" not in names
        assert len(tools) == 2


# ============================================================
# 10. validate_and_execute 完整流程
# ============================================================

class TestValidateAndExecute:
    """validate_and_execute 完整流程测试"""

    def test_success(self, registry_with_tools, mock_context):
        """正常执行流程"""
        result = registry_with_tools.validate_and_execute(
            "bash", {"command": "ls"}, mock_context
        )
        assert result.is_error is False
        assert "executed: ls" in result.output

    def test_not_found(self, mock_context):
        """工具不存在"""
        registry = ToolRegistry()
        result = registry.validate_and_execute(
            "nonexistent", {}, mock_context
        )
        assert result.is_error is True
        assert "不存在" in result.output

    def test_disabled(self, registry_with_tools, mock_context):
        """工具已禁用"""
        result = registry_with_tools.validate_and_execute(
            "disabled_tool", {}, mock_context
        )
        assert result.is_error is True
        assert "禁用" in result.output

    def test_validation_failed(self, mock_context):
        """输入校验失败"""
        registry = ToolRegistry()
        registry.register(build_tool(
            name="test",
            description="test",
            parameters={"type": "object", "properties": {}},
            execute_fn=lambda i, c: ToolResult(output="ok"),
            validate_input=lambda i, c: ValidationResult.failure("缺少 x 参数"),
        ))
        result = registry.validate_and_execute("test", {}, mock_context)
        assert result.is_error is True
        assert "x" in result.output

    def test_permission_denied(self, mock_context):
        """权限被拒绝"""
        registry = ToolRegistry()
        registry.register(build_tool(
            name="test",
            description="test",
            parameters={"type": "object", "properties": {}},
            execute_fn=lambda i, c: ToolResult(output="ok"),
            check_permissions=lambda i, c: PermissionDecision.deny("没有权限"),
        ))
        result = registry.validate_and_execute("test", {}, mock_context)
        assert result.is_error is True
        assert "权限" in result.output

    def test_permission_ask(self, mock_context):
        """需要用户确认（当前返回错误，F04 后会触发交互）"""
        registry = ToolRegistry()
        registry.register(build_tool(
            name="test",
            description="test",
            parameters={"type": "object", "properties": {}},
            execute_fn=lambda i, c: ToolResult(output="ok"),
            check_permissions=lambda i, c: PermissionDecision.ask("确认？"),
        ))
        result = registry.validate_and_execute("test", {}, mock_context)
        assert result.is_error is True
        assert "确认" in result.output

    def test_permission_updated_input(self, mock_context):
        """权限检查修改了 input"""
        registry = ToolRegistry()
        registry.register(build_tool(
            name="test",
            description="test",
            parameters={"type": "object", "properties": {}},
            execute_fn=lambda i, c: ToolResult(output=f"got: {i.get('x')}"),
            check_permissions=lambda i, c: PermissionDecision.allow(
                updated_input={"x": "modified"}
            ),
        ))
        result = registry.validate_and_execute("test", {}, mock_context)
        assert result.is_error is False
        assert "modified" in result.output

    def test_execute_exception(self, mock_context):
        """工具执行时抛出异常"""
        registry = ToolRegistry()

        def bad_execute(input, context):
            raise RuntimeError("boom")

        registry.register(build_tool(
            name="crash",
            description="Crash tool",
            parameters={"type": "object", "properties": {}},
            execute_fn=bad_execute,
        ))
        result = registry.validate_and_execute("crash", {}, mock_context)
        assert result.is_error is True
        assert "RuntimeError" in result.output
        assert "boom" in result.output


# ============================================================
# 11. ToolResult 数据类
# ============================================================

class TestToolResult:
    """ToolResult 数据类测试"""

    def test_basic(self):
        """基本构造"""
        result = ToolResult(output="hello")
        assert result.output == "hello"
        assert result.is_error is False
        assert result.new_messages is None

    def test_error(self):
        """错误结果"""
        result = ToolResult(output="failed", is_error=True)
        assert result.is_error is True

    def test_with_new_messages(self):
        """附带新消息"""
        from agent.core.types import Role, Message
        msg = Message(role=Role.ASSISTANT, content="extra")
        result = ToolResult(output="ok", new_messages=[msg])
        assert len(result.new_messages) == 1  # type: ignore
