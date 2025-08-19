# forma
专为解决非结构化数据处理而设计的后端服务

## 项目结构

```
forma/
├── .gitignore
├── README.md
├── pyproject.toml         # 管理项目和依赖
├── examples/              # 提供一些使用示例脚本
│   └── process_folder.py
└── src/                   # 源代码
    └── forma/             # 可被安装和引用的 Python 包
        ├── __init__.py
        ├── core/          # [心脏] 核心解析逻辑
        │   ├── __init__.py
        │   ├── ocr.py
        │   └── parser.py
        ├── utils/         # 工具函数与文件处理
        │   └── file_handler.py
        └── cli.py         # [新增] CLI 入口和命令定义
```

### 目录说明
- `pyproject.toml`：项目依赖和元数据管理。
- `examples/`：存放项目的实际用例或演示脚本。
- `src/forma/core/`：核心业务逻辑，包括解析与OCR等。
- `src/forma/utils/`：工具函数和通用文件处理。
- `src/forma/cli.py`：命令行入口，统一CLI相关逻辑。

## 使用方法

### 作为命令行工具

```bash
python -m forma
```
或
```bash
python -m forma.cli
```

### 作为包导入

```python
from forma import hello
print(hello("world"))
```

---
如需扩展CLI命令，请在`src/forma/cli.py`中添加。

## 安装说明

基础安装（仅图像 OCR，无 PDF 解析依赖）：

```bash
pip install -e .
```

如需 PDF 解析，请安装可选依赖 `pdf`（包含 PyMuPDF 等）：

```bash
pip install -e .[pdf]
```

使用 uv（推荐，自动生成/使用 uv.lock）：

```bash
# 更新锁文件
uv lock

# 同步基础依赖（不含 PDF）
uv sync

# 同步包含 PDF 额外依赖
uv sync --extra pdf
```

## CLI 使用示例

```bash
# 解析 PDF
forma pdf --input samples/text_only.pdf --output output.md

# 解析单张图片
forma image --input samples/table_image.png --output output.txt
```

## 开发者指南

- `src/forma/core/ocr.py` 使用单例模式管理 `PaddleOCR` 引擎，避免重复加载模型。
- `src/forma/core/parser.py` 在解析 PDF 时并行处理嵌入图片的 OCR，并使用 `tqdm` 显示进度。

提示：未安装 `pdf` 可选依赖时，调用 `parse_scanned_pdf()` 会提示安装 PyMuPDF。
