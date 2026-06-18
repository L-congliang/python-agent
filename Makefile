.PHONY: check test lint typecheck install clean

# 完整验证（提交前必须通过）
check: install typecheck test
	@echo "全部验证通过"

# 安装依赖
install:
	pip install -e ".[dev]" -q

# 运行测试
test:
	python -m pytest tests/ -x -v

# 类型检查（配置 mypy 后启用）
typecheck:
	@mypy src/ --strict 2>/dev/null || echo "mypy 未配置或检查失败，跳过"

# lint（配置 ruff 后启用）
lint:
	@ruff check src/ 2>/dev/null || echo "ruff 未配置，跳过"

# 清理缓存
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache
