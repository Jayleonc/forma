# OCR和PDF处理演示程序

本目录包含三个演示程序，展示如何使用OCR和VLM处理图片和PDF文件。

## 1. 阿里云OCR API演示程序 (aliyun_ocr_demo.py)

这个程序展示如何直接调用阿里云OCR API进行文字识别。

### 使用方法

```bash
# 设置API密钥环境变量
export ALIYUN_OCR_API_KEY="your_api_key_here"

# 处理单个图片
python aliyun_ocr_demo.py /path/to/your/image.jpg

# 指定API密钥并保存结果
python aliyun_ocr_demo.py /path/to/your/image.jpg --api-key "your_api_key_here" --output results.json
```

### 参数说明

- `image_path`: 要处理的图片路径（必需）
- `--api-key`: 阿里云OCR API密钥（可选，如不提供则从环境变量获取）
- `--output`: 输出结果的JSON文件路径（可选）

## 2. OCR通用演示程序 (ocr_demo.py)

这个程序提供了更通用的OCR处理接口，可以处理单个图片或整个目录。

### 使用方法

```bash
# 设置API密钥环境变量
export OCR_API_KEY="your_api_key_here"

# 处理单个图片
python ocr_demo.py /path/to/your/image.jpg

# 处理整个目录中的图片
python ocr_demo.py /path/to/your/images/directory

# 指定API密钥并保存结果
python ocr_demo.py /path/to/your/image.jpg --api-key "your_api_key_here" --output results.txt
```

### 参数说明

- `path`: 图片路径或包含图片的目录路径（必需）
- `--api-key`: OCR API密钥（可选，如不提供则从环境变量获取）
- `--output`: 输出结果的文件路径（可选）

## 3. PDF处理器演示程序 (pdf_processor_demo.py)

这个程序展示如何使用我们的PDF处理器处理PDF文件或单个图片，结合OCR和VLM技术。

### 使用方法

```bash
# 设置VLM API密钥环境变量（通常是OpenAI API密钥）
export FORMA_PAID_OPENAI_API_KEY="your_openai_api_key_here"

# 处理PDF文件
python pdf_processor_demo.py /path/to/your/document.pdf --output-dir ./output

# 处理单个图片
python pdf_processor_demo.py /path/to/your/image.jpg --output-dir ./output

# 仅使用OCR而不使用VLM
python pdf_processor_demo.py /path/to/your/document.pdf --use-ocr

# 调整OCR文本最小字符数阈值
python pdf_processor_demo.py /path/to/your/document.pdf --min-chars 10
```

### 参数说明

- `path`: PDF文件路径或图片路径（必需）
- `--output-dir`: 输出目录（可选）
- `--use-ocr`: 仅使用OCR而不是VLM（可选）
- `--min-chars`: OCR文本最小字符数阈值，默认为8（可选）

## 环境要求

- Python 3.8+
- 依赖库：requests, Pillow, PyMuPDF (fitz)
- 对于VLM功能，需要有效的OpenAI API密钥

## 注意事项

1. 这些演示程序需要有效的API密钥才能正常工作。
2. 处理大型PDF文件或高分辨率图片可能需要较长时间。
3. VLM处理可能会消耗API额度，请注意控制使用量。
