# forma

一个双引擎、智能的文档转换工具集。

`forma` 旨在将不同格式的文档（如 PDF、DOCX、图片）高效地转换为结构化的 Markdown 格式。它内置了“快速”和“深度”双引擎，并提供“自动”策略，能够智能判断文档类型并选择最优处理方式。

## ✨ 核心功能

- **统一的命令行接口**: 所有操作都通过 `forma convert` 命令完成，清晰易用。
- **多种处理策略**: 
  - `fast`: 使用本地解析和 OCR，速度快，适用于文本型文档。
  - `deep`: 调用强大的视觉语言模型（VLM），精准处理扫描件、复杂排版和图片内容。
  - `auto`: 智能路由，自动为每个文件选择 `fast` 或 `deep` 策略。
- **广泛的格式支持**: 支持 PDF、DOCX、PNG、JPG 等常见文档和图片格式。
- **高度可扩展**: 模块化的处理器架构，方便未来添加新的文件格式支持。

## 🚀 快速上手

### 1. 安装

项目提供了 `Makefile` 来简化环境设置和依赖管理，推荐使用此方式。

```bash
# 一键完成虚拟环境创建、依赖锁定和安装
make deps
```

该命令会自动执行以下操作：
1. 创建 `.venv` 虚拟环境。
2. 根据 `pyproject.toml` 生成 `uv.lock` 锁文件。
3. 严格按照锁文件安装所有依赖，确保环境一致性。

### 2. 配置 API 密钥

`deep` 和 `auto` 策略需要使用视觉语言模型，请在项目根目录创建 `.env` 文件并填入您的 API 密钥：

```env
DASHSCOPE_API_KEY="sk-your-api-key-here"
```

### 3. 使用

使用 `convert` 命令进行文档转换。

```bash
# 使用 fast 策略转换单个 PDF
forma convert "./data/pdfs/沐曦招股书.pdf" -o "./output" -s fast

# 使用 deep 策略转换一张图片
forma convert "./data/image/1.png" -o "./output" -s deep

# 使用 auto 策略递归处理整个文件夹
forma convert "./data" -o "./output" -s auto
```

**参数说明:**
- `INPUTS...`: 一个或多个输入文件或文件夹的路径。
- `-o, --output`: 用于保存输出文件的目录。
- `-s, --strategy`: 转换策略，可选值为 `auto`, `fast`, `deep` (默认为 `auto`)。
- `--recursive / --no-recursive`: 是否递归处理子目录 (默认为 `True`)。

## 🛠️ 架构概览

重构后的 `forma` 采用分层、模块化的架构：

```
src/forma/
├── __init__.py
├── cli.py            # 命令行接口 (Typer)
├── config.py         # 配置管理 (Pydantic)
├── controller.py     # 业务流程控制器
├── types.py          # 项目通用类型定义
├── utils/            # 通用工具模块
│   └── docx.py       # DOCX 处理辅助函数
└── core/
    ├── __init__.py
    ├── processors.py # 各文件类型的处理器 (PDF, DOCX, Image)
    └── vlm.py          # 视觉语言模型 (VLM) 抽象层
```

- **`cli.py`**: 定义用户交互的命令行界面。
- **`controller.py`**: 核心协调器，根据用户输入和策略，调用相应的处理器。
- **`processors.py`**: 包含不同文件格式的具体处理逻辑（`fast` 策略）。
- **`vlm.py`**: 封装了对 VLM 的调用（`deep` 策略）。
- **`utils/`**: 存放可重用的辅助函数，如 DOCX 到 Markdown 的转换逻辑。
- **`config.py`**: 负责加载 `.env` 文件中的配置和密钥。

## 💡 工作原理

1.  **`fast` 策略**: 
    - **PDF**: 使用 `pymupdf` 提取文本和图片。对于纯文本 PDF，直接提取；对于扫描件，提取图片后交由 OCR 处理。
    - **DOCX**: 采用混合策略以最大化保留表格等格式。
      1. **优先使用 `mammoth`**：将 DOCX 转换为 HTML，再转换为 Markdown，能较好地还原表格、列表和格式。
      2. **回退至 `python-docx`**：如果前一步失败，则启用基于 `python-docx` 的备用方案，逐一解析段落和表格，确保内容不丢失。
    - **Image**: 使用 `paddleocr` 进行本地 OCR。

2.  **`deep` 策略**: 
    - 将文档页面或图片发送给视觉语言模型（当前使用 `langchain` 集成的 `qwen-vl-max`），由其直接生成详细的 Markdown 描述。

3.  **`auto` 策略**:
    - 首先执行 `fast` 策略。
    - 对结果进行简单分析（如字符数、置信度等）。
    - 如果 `fast` 策略的结果质量不佳（例如，从扫描版 PDF 中只提取到很少的文字），则自动升级，调用 `deep` 策略进行重新处理。
