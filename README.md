# forma

一个双引擎、智能的文档转换工具集。

`forma` 旨在将不同格式的文档（如 PDF、DOCX、图片）高效地转换为结构化的 Markdown 格式。它内置了“快速”和“深度”双引擎，并提供“自动”策略，能够智能判断文档类型并选择最优处理方式。

## ✨ 核心功能

- **统一的命令行接口**: 所有操作都通过 `forma convert` 命令完成，清晰易用。
- **多种处理策略**: 
  - `fast`: 使用本地解析和 OCR，速度快，适用于文本型文档。
  - `deep`: 调用强大的视觉语言模型（VLM），由可定制的提示词驱动，精准处理扫描件、复杂排版和图片内容。
  - `auto`: 智能路由，自动为每个文件选择 `fast` 或 `deep` 策略。
- **广泛的格式支持**: 支持 PDF、DOCX、PPTX、PNG、JPG 等常见文档和图片格式。
- **高度可扩展**: 模块化的处理器架构，方便未来添加新的文件格式支持。
- **提示词工程**: 将提示词与代码分离到 `prompts.yaml`，方便用户按需定制。

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
3.严格按照锁文件安装所有依赖，确保环境一致性。

#### 系统依赖

为了完整支持所有功能，特别是 `.pptx` 文件的深度解析，您需要在系统中安装 `LibreOffice`：

```bash
# macOS
brew install --cask libreoffice

# Ubuntu/Debian
sudo apt-get install libreoffice
```

`forma` 会通过命令行调用 `libreoffice` 来实现 PPTX 到 PDF 的转换。

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
. (项目根目录)
├── prompts.yaml      # VLM 提示词配置文件
└── src/forma/
    ├── __init__.py
    ├── cli.py            # 命令行接口 (Typer)
    ├── config.py         # 配置管理 (Pydantic)
    ├── controller.py     # 业务流程控制器
    ├── types.py          # 项目通用类型定义
    ├── utils/            # 通用工具模块
    └── core/
        ├── __init__.py
        ├── processors.py # 各文件类型的处理器
        ├── prompt_manager.py # 提示词管理器
        └── vlm.py          # 视觉语言模型 (VLM) 抽象层
```

- **`prompts.yaml`**: 定义 `deep` 策略使用的所有提示词，易于修改和扩展。
- **`cli.py`**: 定义用户交互的命令行界面。
- **`controller.py`**: 核心协调器，根据用户输入和策略，调用相应的处理器。
- **`prompt_manager.py`**: 负责从 `prompts.yaml` 加载和管理提示词。
- **`vlm.py`**: 封装对 VLM 的调用，通过 `PromptManager` 获取提示词并发起请求。
- **`config.py`**: 负责加载 `.env` 文件中的配置和密钥。

## 💡 工作原理

1.  **`fast` 策略**: 
    - **PDF**: 使用 `pymupdf` 提取文本和图片。对于纯文本 PDF，直接提取；对于扫描件，提取图片后交由 OCR 处理。
    - **DOCX**: 采用混合策略以最大化保留表格等格式。
      1. **优先使用 `mammoth`**：将 DOCX 转换为 HTML，再转换为 Markdown，能较好地还原表格、列表和格式。
      2. **回退至 `python-docx`**：如果前一步失败，则启用基于 `python-docx` 的备用方案，逐一解析段落和表格，确保内容不丢失。
    - **Image**: 使用 `paddleocr` 进行本地 OCR。
    - **PPTX**: 采用智能的**混合策略**，对每一页幻灯片进行独立分析：
      1. **启发式判断**: 遍历每一页幻灯片，通过计算文本量来判断其是“内容页”还是“复杂页”（如图表、纯图页）。
      2. **内容页处理 (Fast Path)**: 对于文本内容充足的页面，直接使用 `python-pptx` 提取文本，并对页内图片进行 OCR。
      3. **复杂页处理 (Deep Path)**: 对于文本量极少的页面，自动调用深度解析流程：
         - 使用 **`LibreOffice`** 将PPTX转换为PDF。
         - 从PDF中精确提取该复杂页为一张图片。
         - 将此图片交由 **VLM** 进行视觉理解。

2.  **`deep` 策略**: 
    - 将文档页面或图片发送给视觉语言模型（如 `qwen-vl-max`）。
    - 调用过程由 `prompts.yaml` 文件驱动。它会加载一个具名 prompt（默认为 `default_image_description`），该 prompt 包含精心设计的 `system` 和 `user` 指令，引导模型生成高质量的 Markdown 文本。

3.  **`auto` 策略**:
    - 首先执行 `fast` 策略。
    - 对结果进行简单分析（如字符数、置信度等）。
    - 如果 `fast` 策略的结果质量不佳（例如，从扫描版 PDF 中只提取到很少的文字），则自动升级，调用 `deep` 策略进行重新处理。

## 🔧 提示词工程 (Prompt Engineering)

`forma` 的 `deep` 策略的核心是可定制的提示词工程。所有提示词都在项目根目录的 `prompts.yaml` 文件中进行管理，实现了逻辑与提示的分离。

### 文件结构

`prompts.yaml` 结构如下：

```yaml
prompts:
  # 默认的图片/页面描述提示
  default_image_description:
    user: >-
      请详细描述这张图片或页面的内容...

  # 用于分析技术架构图的专用提示
  technical_diagram_analysis:
    system: >-
      你是一位专业的系统架构师...
    user: >-
      请以专业的视角分析这张系统架构图...

  # ... 可添加更多自定义提示
```

### 如何定制

- **修改现有提示**: 直接编辑 `prompts.yaml` 中 `user` 或 `system` 的内容，即可改变模型的行为，无需修改任何 Python 代码。
- **添加新提示**: 你可以按照格式添加新的具名提示（如 `my_custom_prompt`），并在代码中（未来可能通过命令行参数）调用它，以适应特定的文档处理需求。
