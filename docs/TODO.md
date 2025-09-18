# Forma TODO 列表

## PDF 处理改进

- [ ] **改进 PDF 中图片的 OCR 文本整合方式。**
  - **问题：** 目前图片的文字通过 OCR 提取后，被统一追加到文档末尾的“附录”部分。这会打乱原始的文档结构和上下文，尤其在图片是正文关键内容的一部分时影响更大。复杂图片的 OCR 质量也有待提升。
  - **目标：** 不再追加到末尾，而是将 OCR 文本智能地插回到图片在文档中的原始位置，尽量还原原文阅读顺序与上下文。
  - **相关文件：** `src/forma/conversion/processors/pdf.py`

## 可选 OCR 后端：pdf2image + Tesseract（规划）

- [ ] **引入 pdf2image + Tesseract 作为可选后端，不改变现有默认行为。**
  - **现状：** 当前优先使用 `PaddleOCR`（GPU 可加速），无法使用时降级到 `RapidOCR (onnxruntime)`；对中文/复杂版面和结构化（配合 PP-Structure）较友好。
  - **定位：** `pdf2image + Tesseract` 适合对高分辨率、规整的英文/数字印刷体、对依赖较敏感、仅需 CPU 的部署环境；版面重建较弱，需配合图像预处理。
  - **GPU 环境建议：** 若部署在有 GPU 的服务器，优先继续使用 `PaddleOCR` 路线（性能与中文鲁棒性更优）。`Tesseract` 作为备用/切换选项即可。
  - **何时开启开发：**
    - 需要极简依赖（无法安装 Paddle/onnxruntime/OpenCV 等）。
    - 文档以英文印刷体为主，对结构化恢复要求不高。
    - 需要一条纯 CPU、易运维的兜底方案。
  - **任务拆分：**
    - 设计可插拔后端接口，新增 `tesseract` 实现，接口与 `ocr_image_file()` 对齐。
    - 在 `parse_scanned_pdf()` 支持选择渲染器（`PyMuPDF` 或 `pdf2image`）与引擎（`paddle`/`rapid`/`tesseract`）。
    - 增加轻量预处理（阈值/去噪/倾斜矫正/放大）。
    - 提供配置开关（环境变量或 config）：如 `OCR_BACKENDS=paddle,rapid,tesseract` 与优先级。
    - 对中文样本做准确率评估，明确适用范围与告警提示。
  - **相关文件：** `src/forma/ocr/engine.py`, `src/forma/conversion/processors/pdf.py`



## 图片描述插入位置问题

各种文档中包含图片时，图片描述的插入位置需要智能判断，当前有一些格式的处理时直接放在最终md的末尾，可能不太好，调整代码和提示词。


> **image desc 26**: [VLM 调用失败] 这种过滤掉