# Python/uv 项目通用 Makefile（以 uv 为主）
# 目标：每次先 lock，再严格按锁文件安装；支持本地 wheel 仓库避免二次下载
# 使用 'make help' 查看所有可用命令

.DEFAULT_GOAL := help

# 可按需修改
PY_VER ?= 3.12.0
VENV   ?= .venv
LOCK   ?= uv.lock
REQEXP ?= requirements.lock.txt
WHEEL_DIR ?= vendor/wheels
# 使用清华镜像源加速下载
PYPI_MIRROR ?= --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 临时：当网络环境（如VPN/代理）导致TLS握手失败时，设置此环境变量以绕过证书验证
# 警告：这会带来安全风险，应在解决网络问题后移除
export UV_INSECURE=1

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
	@uv lock $(PYPI_MIRROR) $(UV_PLATFORM_FLAGS)

.PHONY: sync
sync:
	@echo ">> uv sync --frozen (strictly install from $(LOCK))"
	@uv sync --frozen $(PYPI_MIRROR) $(UV_PLATFORM_FLAGS)

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
	@uv add $(pkg) $(PYPI_MIRROR)
	@$(MAKE) sync

.PHONY: remove
remove:
	@test -n "$(pkg)" || (echo "Usage: make remove pkg=\"package\""; exit 2)
	@echo ">> uv remove $(pkg)"
	@uv remove $(pkg) $(PYPI_MIRROR)
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
	@uv pip download -r $(REQEXP) -d $(WHEEL_DIR) $(PYPI_MIRROR)

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

# ---------------- Docker 部署 ----------------
IMAGE_NAME ?= forma-service
TAG        ?= latest
CONTAINER_NAME ?= forma
NETWORK_NAME   ?= metax_rag_network
PORT ?= 8090

.PHONY: network
network:
	@docker network inspect $(NETWORK_NAME) >/dev/null 2>&1 || docker network create $(NETWORK_NAME)

.PHONY: docker-build
docker-build:
	@echo ">> building docker image $(IMAGE_NAME):$(TAG)"
	docker build -t $(IMAGE_NAME):$(TAG) .

.PHONY: docker-run
docker-run: network
	@echo ">> starting container $(CONTAINER_NAME) on network $(NETWORK_NAME)"
	docker run -d --rm \
		--name $(CONTAINER_NAME) \
		--network $(NETWORK_NAME) \
		-p $(PORT):$(PORT) \
		$(IMAGE_NAME):$(TAG)

.PHONY: docker-stop
docker-stop:
	@echo ">> stopping container $(CONTAINER_NAME)"
	@docker rm -f $(CONTAINER_NAME) >/dev/null 2>&1 || true

.PHONY: docker-logs
docker-logs:
	@docker logs -f $(CONTAINER_NAME)

# ---------------- 本地服务运行 ----------------
# 服务配置（可通过环境变量覆盖）
HOST ?= 0.0.0.0
SERVER_PORT ?= 8090
WORKERS ?= 1
CONVERSION_WORKERS ?= 4
QA_WORKERS ?= 2
LOG_LEVEL ?= INFO

.PHONY: serve
serve:
	@echo "========================================"
	@echo "  启动 Forma API 服务"
	@echo "========================================"
	@echo "配置:"
	@echo "  - 监听地址: $(HOST):$(SERVER_PORT)"
	@echo "  - Uvicorn Workers: $(WORKERS)"
	@echo "  - Conversion Workers: $(CONVERSION_WORKERS)"
	@echo "  - QA Workers: $(QA_WORKERS)"
	@echo "  - 日志级别: $(LOG_LEVEL)"
	@echo "========================================"
	@echo ""
	@CONVERSION_WORKERS=$(CONVERSION_WORKERS) \
	QA_WORKERS=$(QA_WORKERS) \
	LOG_LEVEL=$(LOG_LEVEL) \
	uv run uvicorn forma.server:app \
		--host $(HOST) \
		--port $(SERVER_PORT) \
		--workers $(WORKERS)

.PHONY: serve-dev
serve-dev:
	@echo "========================================"
	@echo "  启动 Forma API 服务 (开发模式)"
	@echo "========================================"
	@echo "配置:"
	@echo "  - 监听地址: $(HOST):$(SERVER_PORT)"
	@echo "  - 热重载: 已启用"
	@echo "  - Conversion Workers: $(CONVERSION_WORKERS)"
	@echo "  - QA Workers: $(QA_WORKERS)"
	@echo "  - 日志级别: DEBUG"
	@echo "========================================"
	@echo ""
	@CONVERSION_WORKERS=$(CONVERSION_WORKERS) \
	QA_WORKERS=$(QA_WORKERS) \
	LOG_LEVEL=DEBUG \
	uv run uvicorn forma.server:app \
		--host $(HOST) \
		--port $(SERVER_PORT) \
		--reload

.PHONY: help
help:
	@echo "========================================"
	@echo "  Forma 项目 Makefile 帮助"
	@echo "========================================"
	@echo ""
	@echo "📦 依赖管理:"
	@echo "  make deps          - 一键安装所有依赖（推荐首次使用）"
	@echo "  make venv          - 创建虚拟环境"
	@echo "  make lock          - 锁定依赖版本"
	@echo "  make sync          - 同步安装依赖"
	@echo "  make add pkg=XXX   - 添加新依赖"
	@echo "  make remove pkg=XXX- 移除依赖"
	@echo ""
	@echo "🚀 服务运行:"
	@echo "  make serve         - 启动 API 服务（生产模式）"
	@echo "  make serve-dev     - 启动 API 服务（开发模式，热重载+DEBUG日志）"
	@echo ""
	@echo "  环境变量配置示例:"
	@echo "    make serve HOST=0.0.0.0 SERVER_PORT=8090 CONVERSION_WORKERS=8 QA_WORKERS=4 LOG_LEVEL=INFO"
	@echo ""
	@echo "🧪 开发工具:"
	@echo "  make test          - 运行测试"
	@echo "  make lint          - 代码检查"
	@echo "  make format        - 代码格式化"
	@echo "  make quality       - 运行 lint + test"
	@echo ""
	@echo "🐳 Docker 部署:"
	@echo "  make docker-build  - 构建 Docker 镜像"
	@echo "  make docker-run    - 运行 Docker 容器"
	@echo "  make docker-stop   - 停止 Docker 容器"
	@echo "  make docker-logs   - 查看容器日志"
	@echo ""
	@echo "🛠️  维护:"
	@echo "  make doctor        - 诊断环境信息"
	@echo "  make clean         - 清理临时文件和缓存"
	@echo "  make export        - 导出依赖清单"
	@echo "  make wheels        - 预下载 wheel 包"
	@echo ""
	@echo "========================================"
