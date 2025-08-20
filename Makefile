# Python/uv 项目通用 Makefile（以 uv 为主）
# 目标：每次先 lock，再严格按锁文件安装；支持本地 wheel 仓库避免二次下载

# 可按需修改
PY_VER ?= 3.12.0
VENV   ?= .venv
LOCK   ?= uv.lock
REQEXP ?= requirements.lock.txt
WHEEL_DIR ?= vendor/wheels

# Detect OS for platform-specific flags
UNAME_S := $(shell uname -s)
UV_PLATFORM_FLAGS :=
ifeq ($(UNAME_S),Linux)
	# For Linux, add PyTorch's CUDA 12.1 index. Adjust cuXXX as needed.
	UV_PLATFORM_FLAGS += --extra-index-url https://download.pytorch.org/whl/cu121
endif

# ------------- 基础 -------------
.PHONY: venv
venv:
	@echo ">> ensure pyenv local $(PY_VER) and create $(VENV)"
	@pyenv local $(PY_VER)
	@uv venv $(VENV)

.PHONY: lock
lock:
	@echo ">> uv lock (resolve deps into $(LOCK))"
	@uv lock $(UV_PLATFORM_FLAGS)

.PHONY: sync
sync:
	@echo ">> uv sync --frozen (strictly install from $(LOCK))"
	@uv sync --frozen $(UV_PLATFORM_FLAGS)

# 一键：先 lock 再 sync（默认推荐用这个）
.PHONY: deps
deps: venv lock sync

# ------------- 依赖变更 -------------
# 用法：
#   make add pkg="fastapi==0.115.0"
#   make remove pkg="fastapi"
.PHONY: add
add:
	@test -n "$(pkg)" || (echo "Usage: make add pkg=\"package[==ver]\""; exit 2)
	@echo ">> uv add $(pkg)"
	@uv add $(pkg)
	@$(MAKE) sync

.PHONY: remove
remove:
	@test -n "$(pkg)" || (echo "Usage: make remove pkg=\"package\""; exit 2)
	@echo ">> uv remove $(pkg)"
	@uv remove $(pkg)
	@$(MAKE) sync

# ------------- 导出 & 离线安装支持 -------------
# 导出锁定清单（精确版本），便于 wheel 预下载/离线安装
.PHONY: export
export:
	@echo ">> uv export -o $(REQEXP)"
	@uv export -o $(REQEXP)

# 预下载 wheel 到本地仓库；下次换版本/回退优先用本地，不走网络
.PHONY: wheels
wheels: export
	@echo ">> pre-download wheels to $(WHEEL_DIR)"
	@mkdir -p $(WHEEL_DIR)
	@uv pip download -r $(REQEXP) -d $(WHEEL_DIR)

# 完全离线/半离线安装（优先本地 wheel 仓）
.PHONY: offline-sync
offline-sync: export
	@echo ">> offline install from $(WHEEL_DIR)"
	@uv pip install --no-index --find-links=$(WHEEL_DIR) -r $(REQEXP)

# ------------- 维护 -------------
.PHONY: freeze
freeze:
	@echo ">> freeze to $(REQEXP) (from lock)"
	@uv export -o $(REQEXP)

.PHONY: doctor
doctor:
	@echo "=== interpreter ==="; \
	command -v python; python --version; \
	echo "python executable: $$(python -c 'import sys; print(sys.executable)')"; \
	echo; \
	echo "=== uv ==="; uv --version; uv cache dir; \
	echo; \
	echo "=== venv pip list (top 40) ==="; \
	if [ -d "$(VENV)" ]; then . $(VENV)/bin/activate; pip list | head -n 40; else echo "no $(VENV) yet"; fi

.PHONY: test
test:
	@echo ">> running tests with pytest"
	@uv run pytest

.PHONY: lint
lint:
	@echo ">> linting with ruff"
	@uv run ruff check .

.PHONY: format
format:
	@echo ">> formatting with ruff"
	@uv run ruff format .

.PHONY: quality
quality: lint test

.PHONY: clean
clean:
	@echo ">> removing venv, cache, and build artifacts"
	@rm -rf $(VENV) .venv .pytest_cache .ruff_cache build dist *.egg-info
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "Clean complete."