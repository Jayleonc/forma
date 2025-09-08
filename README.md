# forma

一个双引擎、智能的文档转换工具集。

`forma` 旨在将不同格式的文档（如 PDF、DOCX、图片）高效地转换为结构化的 Markdown 格式。它内置了“快速”和“深度”双引擎，并提供“自动”策略，能够智能判断文档类型并选择最优处理方式。

## ✨ 核心功能

- **统一的命令行接口**: 所有操作都通过 `forma convert` 和 `forma generate-qa` 命令完成，清晰易用。
- **多种处理策略**:
  - `fast`: 使用本地解析和 OCR，速度快，适用于文本型文档。
  - `deep`: 调用强大的视觉语言模型（VLM），由可定制的提示词驱动，精准处理扫描件、复杂排版和图片内容。
  - `auto`: 智能路由，自动为每个文件选择 `fast` 或 `deep` 策略。
- **广泛的格式支持**: 支持 PDF、DOCX、PPTX、PNG、JPG 等常见文档和图片格式。
- **高度可扩展**: 采用按功能划分的模块化包结构，方便未来添加新的文件格式支持和功能。
- **提示词工程**: 将提示词与代码分离到 `prompts.yaml`，方便用户按需定制。
- **异步微服务**: 提供 `/api/v1/convert` 接口，接受包含 `request_id`、`source_url` 和 `callback_url` 的 JSON 请求，立即返回 `task_id`，转换完成后以回调方式返回结果。

## 🚀 快速上手

### 1. 安装

项目提供了 `Makefile` 来简化环境设置和依赖管理，推荐使用此方式。

```bash
# 一键完成虚拟环境创建、依赖锁定和安装
make deps
```

该命令会自动执行以下操作：

1.  创建 `.venv` 虚拟环境。
2.  根据 `pyproject.toml` 和当前操作系统，智能解析并锁定依赖。
3.  严格按照锁文件安装所有依赖，确保环境一致性。

**自动硬件加速**:

`make deps` 命令会自动检测您的操作系统，并安装最优的依赖包：

- **Linux**: 自动安装 `paddlepaddle-gpu` 和 `torch` 的 CUDA 版本，以启用 GPU 加速。
- **macOS / Windows**: 安装标准的 CPU 版本。

您无需任何手动配置，即可在支持的硬件上获得最佳性能。

#### 系统依赖 (可选)

**`LibreOffice` (可选，用于增强 PPTX 解析)**

`forma` 可以不依赖任何外部软件运行。但为了解锁对 `.pptx` 文件中复杂幻灯片（如图表、纯图片页面）的完整深度解析功能，需要安装 `LibreOffice`。

- **如果已安装 `LibreOffice`**: `forma` 会自动检测并使用它来转换复杂幻灯片，以获得最精准的分析结果。
- **如果未安装 `LibreOffice`**: `forma` 仍然可以正常处理所有文件的文本内容。对于 PPTX 中的复杂幻灯片，它将跳过深度解析，并在输出的 Markdown 文件中插入一条提示信息，不会因此中断或报错。

**安装方法:**

- **macOS (使用 Homebrew):**
  ```bash
  brew install --cask libreoffice
  ```

- **Linux (Ubuntu/Debian):**
  ```bash
  sudo apt-get update && sudo apt-get install -y libreoffice
  ```

### 2. 配置 API 密钥

`deep` 和 `auto` 策略需要使用视觉语言模型。请在项目根目录创建 `.env` 文件并填入您的 API 密钥：

```env
# 请填入您的 OpenAI API 密钥
FORMA_OPENAI_API_KEY="sk-your-api-key-here"

# 或者，您也可以使用 VLM_API_KEY 变量名
# VLM_API_KEY="sk-your-api-key-here"
```

### 3. 使用

使用 `convert` 命令进行文档转换。

```bash
# 使用 fast 策略转换单个 PDF
uv run forma convert "./data/pdfs/沐曦招股书.pdf" -o "./output" -s fast

# 使用 deep 策略转换一张图片
uv run forma convert "./data/image/1.png" -o "./output" -s deep

# 使用 auto 策略递归处理整个文件夹 (默认策略)
uv run forma convert "./data" -o "./output"

# 使用自定义提示词进行深度分析
uv run forma convert "./data/image/1.png" -o "./output" -s deep -p "technical_diagram_analysis"
```

**参数说明:**

- `INPUTS...`: 一个或多个输入文件或文件夹的路径。
- `-o, --output`: 用于保存输出文件的目录。
- `-s, --strategy`: 转换策略，可选值为 `auto`, `fast`, `deep` (默认为 `auto`)。
- `-p, --prompt`: 指定 `deep` 或 `auto` 策略要使用的提示词名称 (默认为 `default_image_description`)。
- `--recursive / --no-recursive`: 是否递归处理子目录 (默认为 `True`)。

## 🛠️ 架构概览

`forma` 采用按功能组织的包结构，清晰地分离了不同的业务领域：

```
. (项目根目录)
├── prompts.yaml      # VLM 提示词配置文件
└── src/forma/
    ├── __init__.py
    ├── cli.py            # 命令行接口 (Typer)
    ├── conversion/       # 核心功能：文档转换
    │   ├── __init__.py
    │   ├── workflow.py     # 转换流程的业务逻辑编排
    │   └── processors/     # 针对不同文件类型（PDF, DOCX等）的具体处理器
    ├── ocr/              # 核心功能：光学字符识别（OCR）
    │   ├── __init__.py
    │   └── engine.py       # OCR 引擎的封装
    ├── qa/               # 核心功能：问答对（QA）生成
    │   ├── __init__.py
    │   ├── builder.py      # QA 对的构建逻辑
    │   └── pipeline.py     # QA 生成的完整流水线
    ├── shared/           # 跨功能共享的模块
    │   ├── __init__.py
    │   ├── config.py       # 配置管理 (Pydantic)
    │   ├── prompts.py      # 提示词管理器
    │   └── utils/          # 通用工具函数
    └── vision/           # 核心功能：视觉语言模型（VLM）交互
        ├── __init__.py
        ├── client.py       # VLM API 客户端
        └── parser.py       # VLM 响应解析器
```

- **`cli.py`**: 定义用户交互的命令行界面。
- **`prompts.yaml`**: 定义 `deep` 策略使用的所有提示词，易于修改和扩展。
- **`conversion/`**: 包含所有与文档格式转换相关的逻辑。
- **`ocr/`**: 封装了 OCR 功能，供其他模块调用。
- **`qa/`**: 实现了从文本生成结构化问答对的完整流程。
- **`vision/`**: 负责与视觉语言模型进行交互，是 `deep` 策略的核心。
- **`shared/`**: 存放被多个功能包共享的通用代码，如配置加载、工具函数等。

## 💡 工作原理

1.  **`fast` 策略**:

    - **PDF**: 使用 `pymupdf` 提取文本和图片。对于纯文本 PDF，直接提取；对于扫描件，提取图片后交由 `ocr` 模块处理。
    - **DOCX**: 采用混合策略以最大化保留表格等格式。
      1. **优先使用 `mammoth`**：将 DOCX 转换为 HTML，再转换为 Markdown，能较好地还原表格、列表和格式。
      2. **回退至 `python-docx`**：如果前一步失败，则启用基于 `python-docx` 的备用方案，逐一解析段落和表格，确保内容不丢失。
    - **Image**: 使用 `ocr` 模块进行本地 OCR。
    - **PPTX**: 采用更智能的**混合策略**，对每一页幻灯片进行独立分析：
      1. **智能决策**: 遍历每一页幻灯片，分析其内容构成来判断是“内容页”还是“复杂页”。
         - **优先识别复杂对象**: 如果幻灯片包含 **图表 (Chart)**、**SmartArt** 或 **表格 (Table)**，则立即判定为“复杂页”。
         - **分析图文关系**: 如果页面主要是图片，文字极少，也判定为“复杂页”。
      2. **内容页处理 (Fast Path)**: 对于文本密集型页面，直接使用 `python-pptx` 提取文本，并对页内图片进行 OCR。
      3. **复杂页处理 (Deep Path)**: 对于“复杂页”，自动调用深度解析流程：
         - 使用 **`LibreOffice`** (如果可用) 将其渲染为高清图片。
         - 将此图片交由 `vision` 模块进行视觉理解。

2.  **`deep` 策略**:

    - 将文档页面或图片发送给 `vision` 模块。
    - 调用过程由 `prompts.yaml` 文件驱动，引导模型生成高质量的 Markdown 文本。

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
- **添加新提示**: 你可以按照格式添加新的具名提示（如 `my_custom_prompt`），然后通过 `-p` 或 `--prompt` 命令行参数来调用它，以适应特定的文档处理需求。

## 🧑‍💻 开发与测试

项目使用 `pytest` 进行测试。运行以下命令以执行完整的测试套件：

```bash
make test
```

这会运行 `tests/` 目录下的所有测试用例，并生成覆盖率报告。

## ✨ 特性亮点: `generate-qa` 命令

`forma` 提供了一个强大的 `generate-qa` 命令，可以将任何 Markdown 文档转换为结构化的、高质量的常见问题（FAQ）列表，并以 CSV 格式导出。这背后是一套精心设计的三阶段智能流水线。

### 工作原理：三阶段流水线

1.  **阶段一：原始问答生成**

    - 系统首先将 Markdown 文档切分为多个内容块。
    - 针对每个块，调用大语言模型（LLM）初步提取独立的问答对（QA-Pairs）。

2.  **阶段二：全局分类体系生成**

    - 收集上一阶段生成的所有问题。
    - 再次调用 LLM，分析这些问题并总结出 5-8 个核心主题分类，形成一个全局的知识体系结构。

3.  **阶段三：合成、聚类与指派**
    - 这是流水线的核心，它通过一个“向量化 -> 聚类 -> LLM 合成”的精密流程，将原始问答对提炼升华。
    - **向量化 (`sentence-transformers`)**: 使用 `sentence-transformers` 框架将所有原始问题的文本高效地转换为高质量的数学向量（Embeddings）。我们选择这个框架是因为它 API 简洁、专门为句子/段落设计、且支持完全本地化部署，保障数据隐私。
    - **语义聚类 (`DBSCAN`)**: 接收上一步生成的向量，并使用 `DBSCAN` 算法进行语义聚类。`DBSCAN` 的优势在于无需预设簇的数量，能根据问题本身的语义密度自动发现主题分组，并能有效识别和过滤“噪音”问题。
    - **合成与指派 (LLM)**: 将每个语义相近的问题簇（Cluster）分别提交给 LLM，执行更高层次的“总结”和“提炼”任务，最终产出唯一的、高质量的、已归类的标准问答对。

这个设计将计算密集型任务（如向量化、聚类）交给高效的开源库处理，而将需要深度语义理解和创造性的任务（内容合成）交给强大的 LLM，实现了成本和质量的最佳平衡。
