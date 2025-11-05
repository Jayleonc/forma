# Forma 生产部署指南

## 1. 概述

**本指南旨在提供一个官方推荐的生产环境部署范例。** 您可以将其作为参考，并根据您企业内部的标准化部署流程（如使用自定义基础镜像、接入内部 CI/CD 等）进行调整。本地开发环境的快速启动说明请参考项目根目录的 [README.md](./README.md)。

### 1.1 系统简介

**Forma** 是一个基于 Python 开发的双引擎、智能文档转换微服务。它的核心功能是将多种格式的文档（如 PDF、DOCX、图片）高效地转换为结构化的 Markdown 格式。

在 Metax RAG 服务生态中，Forma 作为一个独立的、必要的依赖服务运行，专门负责处理由 **Metax RAG** 服务分发来的文档转换任务。

### 1.2 服务架构与依赖关系

**服务协作流程：**

1. Metax RAG 接收用户上传的文档
2. Metax RAG 通过 HTTP API 将文档 URL 发送给 Forma 服务
3. Forma 下载文档并执行转换（使用 fast/deep/auto 策略）
4. Forma 通过回调接口将转换后的 Markdown 内容返回给 Metax RAG
5. Metax RAG 对 Markdown 内容进行向量化并存储

这种异步回调架构使得文档转换过程不会阻塞主服务，提高了系统的整体吞吐量和可靠性。

---

## 2. 环境准备

建议您的生产环境满足以下要求：

### 必需软件及版本

| 软件 | 推荐版本 | 说明 |
|------|---------|------|
| **Python** | 3.12+ | Python 编程语言运行时 |
| **Docker** (可选) | 20.10+ | 容器化部署工具，推荐用于生产环境 |

### 可选依赖

| 软件 | 说明 |
|------|------|
| **LibreOffice** | 用于增强对 PPTX 文件中复杂幻灯片（如图表）的深度解析能力。如果不需要处理复杂的 PPTX 文件，则此项不是必需的。 |

**安装 LibreOffice（可选）：**

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y libreoffice

# macOS
brew install --cask libreoffice
```

### 网络端口

默认使用以下端口（可根据实际情况调整）：

- **8090**: Forma 服务默认端口

---

## 3. 服务配置

Forma 服务通过**环境变量**进行配置。在容器化部署时，可以将这些变量直接注入到容器中。

### 3.1 核心配置项

| 环境变量 | 说明 | 默认值 | 示例 |
|---------|------|--------|------|
| **FORMA_OPENAI_API_KEY** | 用于"深度"解析模式的视觉语言模型（VLM）的 API 密钥 | - | `sk-your-api-key` |
| **LOG_LEVEL** | 日志级别 | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| **FORMA_CONVERSION_TIMEOUT** | 文档转换超时时间（秒） | `600` | `1200` |
| **FORMA_QA_TIMEOUT** | 知识库生成超时时间（秒） | `600` | `1200` |
| **FORMA_DATA_DIR** | 数据保存目录 | `./data` | `/app/data` |
| **CONVERSION_WORKERS** | 文档转换并发 worker 数量 | `4` | `8` |
| **QA_WORKERS** | 知识库生成并发 worker 数量 | `2` | `4` |

### 3.2 可选配置项

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| **VLM_BASE_URL** | VLM 服务基础 URL（如使用自定义端点） | - |
| **VLM_MODEL** | VLM 模型名称 | `gpt-4o` |
| **VLM_AUTO_THRESHOLD** | AUTO 策略阈值（字符数） | `100` |

### 3.3 配置文件示例

您可以创建 `.env` 文件来管理环境变量：

```env
# API 密钥配置
FORMA_OPENAI_API_KEY=sk-your-api-key-here

# 服务配置
LOG_LEVEL=INFO
FORMA_CONVERSION_TIMEOUT=600
FORMA_QA_TIMEOUT=600
FORMA_DATA_DIR=./data

# Worker 配置
CONVERSION_WORKERS=4
QA_WORKERS=2
```

---

## 4. 容器化部署

### 4.1 Forma 镜像构建与运行

#### 4.1.1 Dockerfile 参考

```dockerfile
# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local
COPY prompts.yaml ./
COPY . .

EXPOSE 8090

CMD ["uvicorn", "forma.server:app", "--host", "0.0.0.0", "--port", "8090"]
```

**关键设计说明：**

1. **多阶段构建**：分离构建和运行环境，减小最终镜像体积。
2. **系统依赖**：安装 `libgl1` 和 `libglib2.0-0` 以支持图像处理库（如 OpenCV）。
3. **Python 优化**：设置 `PYTHONDONTWRITEBYTECODE` 和 `PYTHONUNBUFFERED` 环境变量，优化容器内 Python 运行。

**可选：添加 LibreOffice 支持**

如需在容器中支持复杂 PPTX 解析，可在 runtime 阶段添加：

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libgl1 libglib2.0-0 libreoffice \
    && rm -rf /var/lib/apt/lists/*
```

#### 4.1.2 构建镜像

可以参考以下命令构建镜像：

```bash
docker build -t forma:latest .
```

**注意：** 您也可以根据企业内部标准，使用自定义的基础镜像或调整构建参数。

#### 4.1.3 运行容器

**基础运行示例：**

```bash
docker run -d \
  --name forma_service \
  -p 8090:8090 \
  -e FORMA_OPENAI_API_KEY="sk-your-api-key-here" \
  forma:latest
```

**生产环境运行示例：**

```bash
# 创建自定义网络（用于与 Metax RAG 服务通信，可选）
docker network create metax_network

# 运行容器（参数可根据实际需求调整）
docker run -d \
  --name forma_service \
  --network metax_network \
  -p 8090:8090 \
  -e FORMA_OPENAI_API_KEY="sk-your-api-key-here" \
  -e LOG_LEVEL=INFO \
  -e CONVERSION_WORKERS=8 \
  -e QA_WORKERS=4 \
  -v /mnt/data/forma:/app/data \
  --restart unless-stopped \
  forma:latest
```

**参数说明：**

- `--network metax_network`: 指定自定义网络，允许与 Metax RAG 服务通信
- `-e FORMA_OPENAI_API_KEY`: 通过环境变量传入 API 密钥
- `--name forma_service`: 为容器指定一个固定的、可预测的服务名
- `-v /mnt/data/forma:/app/data`: 挂载数据目录（可选）
- `--restart unless-stopped`: 自动重启策略

#### 4.1.4 验证部署

可以通过以下命令验证部署状态：

```bash
# 查看容器状态
docker ps | grep forma

# 查看容器日志
docker logs -f forma_service

# 测试健康检查（如果服务提供健康检查端点）
curl http://localhost:8090/health
```

---

## 5. 与 Metax RAG 集成

要让 Metax RAG 服务能够正确调用 Forma，您必须完成以下关键配置：

### 5.1 网络连接

**确保 Metax RAG 和 Forma 两个容器运行在同一个 Docker 网络下**（如上文中的 `metax_network`）。

```bash
# 如果尚未创建网络
docker network create metax_network

# 确认两个容器都连接到该网络
docker network inspect metax_network
```

### 5.2 配置 Metax RAG

在 **Metax RAG** 服务的 `configs/config.yaml` 文件中，找到 `forma` 配置块，并将其 `host` 字段指向 Forma 容器的服务名和端口。

**配置示例 (metax_rag/configs/config.yaml):**

```yaml
forma:
  host: "http://forma_service:8090"  # 必须与 Forma 容器的服务名匹配
```

**关键说明：**

- `forma_service` 是 Forma 容器的名称（通过 `--name` 参数指定）
- `8090` 是 Forma 服务的内部端口
- 在 Docker 网络内，容器可以通过服务名进行通信，无需使用 IP 地址

### 5.3 集成验证

**步骤 1：确认网络连接**

```bash
# 从 Metax RAG 容器内测试连接
docker exec -it metax_rag_server sh
# 在容器内执行
wget -O- http://forma_service:8090/health
```

**步骤 2：测试文档转换**

通过 Metax RAG 的 API 上传一个测试文档，观察日志确认 Forma 服务是否被正确调用：

```bash
# 查看 Forma 服务日志
docker logs -f forma_service

# 查看 Metax RAG 服务日志
docker logs -f metax_rag_server
```

---

## 6. 服务监控与维护

### 6.1 日志管理

**查看实时日志：**

```bash
docker logs -f forma_service
```

**查看详细调试日志：**

```bash
# 重启容器并设置 DEBUG 日志级别
docker stop forma_service
docker rm forma_service

docker run -d \
  --name forma_service \
  --network metax_network \
  -p 8090:8090 \
  -e FORMA_OPENAI_API_KEY="sk-your-api-key-here" \
  -e LOG_LEVEL=DEBUG \
  --restart unless-stopped \
  forma:latest
```

### 6.2 性能调优

**调整 Worker 数量：**

根据服务器 CPU 核心数和负载情况，建议调整并发 worker 数量：

```bash
docker run -d \
  --name forma_service \
  --network metax_network \
  -p 8090:8090 \
  -e FORMA_OPENAI_API_KEY="sk-your-api-key-here" \
  -e CONVERSION_WORKERS=8 \
  -e QA_WORKERS=4 \
  --restart unless-stopped \
  forma:latest
```

**调整超时时间：**

对于大型文档，建议增加超时时间：

```bash
-e FORMA_CONVERSION_TIMEOUT=1200 \
-e FORMA_QA_TIMEOUT=1200
```

### 6.3 数据持久化

建议挂载数据目录以保存转换结果和日志：

```bash
docker run -d \
  --name forma_service \
  --network metax_network \
  -p 8090:8090 \
  -e FORMA_OPENAI_API_KEY="sk-your-api-key-here" \
  -v /mnt/data/forma:/app/data \
  --restart unless-stopped \
  forma:latest
```

---

## 7. 常见问题

### 7.1 如何更新配置？

Forma 使用环境变量配置，更新配置需要重启容器：

```bash
# 停止并删除旧容器
docker stop forma_service
docker rm forma_service

# 使用新配置启动容器
docker run -d \
  --name forma_service \
  --network metax_network \
  -p 8090:8090 \
  -e FORMA_OPENAI_API_KEY="new-api-key" \
  -e CONVERSION_WORKERS=16 \
  --restart unless-stopped \
  forma:latest
```

### 7.2 Metax RAG 无法连接到 Forma 服务

**检查清单：**

1. 确认两个容器在同一 Docker 网络中
2. 确认 Forma 容器名称与 Metax RAG 配置中的 `forma.host` 匹配
3. 确认 Forma 服务正常运行（`docker logs forma_service`）
4. 在 Metax RAG 容器内测试连接（`docker exec -it metax_rag_server wget -O- http://forma_service:8090/health`）

### 7.3 文档转换超时

**解决方案：**

1. 增加超时时间：`-e FORMA_CONVERSION_TIMEOUT=1200`
2. 增加 worker 数量：`-e CONVERSION_WORKERS=8`
3. 检查 API 密钥是否正确配置
4. 查看详细日志：`-e LOG_LEVEL=DEBUG`

### 7.4 如何处理复杂 PPTX 文件？

**解决方案：**

在 Dockerfile 中添加 LibreOffice 支持，然后重新构建镜像：

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libgl1 libglib2.0-0 libreoffice \
    && rm -rf /var/lib/apt/lists/*
```

---

## 8. 小结

本指南提供了 **Forma 文档转换服务**的生产部署参考，包括：

✅ 系统概述与服务架构  
✅ 环境依赖说明  
✅ 配置项详解  
✅ 容器化部署示例  
✅ 与 Metax RAG 集成配置  
✅ 服务监控与维护

**关键集成要点：**

1. 确保 Forma 和 Metax RAG 容器在同一 Docker 网络中
2. 在 Metax RAG 的 `config.yaml` 中配置 `forma.host: "http://forma_service:8090"`
3. 通过环境变量 `FORMA_OPENAI_API_KEY` 配置 API 密钥

**提示：** 本指南提供的是推荐配置和命令示例，您应该根据企业内部的标准化流程（如 Kubernetes 部署、CI/CD 集成等）进行相应调整。

---

**相关文档：**

- [Forma README.md](./README.md) - 本地开发和 CLI 使用指南
- [Metax RAG 部署指南](../metax_rag/DEPLOYMENT_GUIDE.md) - Metax RAG 服务部署说明
