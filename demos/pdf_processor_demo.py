#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PDF处理器演示程序：展示如何使用VLM和OCR处理图片
"""

import os
import sys
import argparse
from pathlib import Path
import tempfile
import shutil

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.forma.conversion.processors.pdf import PdfProcessor
from src.forma.vision import VLMClient
from src.forma.shared.config import get_vlm_config
from src.forma.ocr import ocr_image_file


def process_single_image(image_path, use_vlm=True, min_text_chars=8):
    """
    处理单个图片，使用OCR和可选的VLM
    
    Args:
        image_path: 图片路径
        use_vlm: 是否使用VLM
        min_text_chars: OCR文本最小字符数阈值
    
    Returns:
        处理结果
    """
    print(f"正在处理图片: {Path(image_path).name}")
    
    # 首先使用OCR处理图片
    try:
        ocr_result = ocr_image_file(str(image_path))
        print(f"OCR结果 ({len(ocr_result.strip())} 字符):")
        print("-" * 40)
        print(ocr_result)
        print("-" * 40)
    except Exception as e:
        print(f"OCR处理失败: {e}")
        ocr_result = ""
    
    # 如果启用VLM且OCR文本足够长，使用VLM处理
    if use_vlm and len(ocr_result.strip()) >= min_text_chars:
        try:
            # 创建VLM客户端
            config = get_vlm_config()
            vlm_client = VLMClient(
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url
            )
            
            # 使用VLM处理图片
            vlm_result = vlm_client.describe(image_path, prompt_name="pdf_image_description")
            print(f"VLM结果 ({len(vlm_result.strip())} 字符):")
            print("-" * 40)
            print(vlm_result)
            print("-" * 40)
            
            return {
                "ocr_result": ocr_result,
                "vlm_result": vlm_result
            }
        except Exception as e:
            print(f"VLM处理失败: {e}")
    
    return {
        "ocr_result": ocr_result,
        "vlm_result": None
    }


def process_pdf_with_images(pdf_path, output_dir=None, use_ocr=False):
    """
    使用PDF处理器处理PDF文件
    
    Args:
        pdf_path: PDF文件路径
        output_dir: 输出目录，如果为None则使用临时目录
        use_ocr: 是否仅使用OCR而不是VLM
    
    Returns:
        处理结果的Markdown内容
    """
    print(f"正在处理PDF: {Path(pdf_path).name}")
    
    # 创建VLM客户端
    try:
        config = get_vlm_config()
        vlm_client = VLMClient(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url
        )
    except Exception as e:
        print(f"创建VLM客户端失败: {e}")
        vlm_client = None
        use_ocr = True  # 如果VLM客户端创建失败，强制使用OCR
    
    # 创建PDF处理器
    processor = PdfProcessor(vlm_client=vlm_client, use_ocr=use_ocr, min_text_chars=8)
    
    # 如果没有指定输出目录，使用临时目录
    if output_dir is None:
        temp_dir = tempfile.mkdtemp()
        output_dir = Path(temp_dir)
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True, parents=True)
    
    try:
        # 处理PDF
        result = processor.process(Path(pdf_path))
        
        # 保存结果
        output_file = output_dir / f"{Path(pdf_path).stem}.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(result.markdown_content)
        
        print(f"处理完成，结果已保存到: {output_file}")
        print(f"文本字符数: {result.text_char_count}")
        print(f"图片数量: {result.image_count}")
        
        return result.markdown_content
    except Exception as e:
        print(f"处理PDF时出错: {e}")
        return None


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="PDF处理器演示程序")
    parser.add_argument("path", help="PDF文件路径或图片路径")
    parser.add_argument("--output-dir", help="输出目录")
    parser.add_argument("--use-ocr", action="store_true", help="仅使用OCR而不是VLM")
    parser.add_argument("--min-chars", type=int, default=8, help="OCR文本最小字符数阈值")
    
    args = parser.parse_args()
    
    path = Path(args.path)
    
    if not path.exists():
        print(f"文件不存在: {path}")
        return
    
    # 根据文件类型选择处理方式
    if path.suffix.lower() == '.pdf':
        # 处理PDF文件
        process_pdf_with_images(
            pdf_path=str(path),
            output_dir=args.output_dir,
            use_ocr=args.use_ocr
        )
    elif path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']:
        # 处理单个图片
        result = process_single_image(
            image_path=str(path),
            use_vlm=not args.use_ocr,
            min_text_chars=args.min_chars
        )
        
        # 保存结果
        if args.output_dir:
            output_dir = Path(args.output_dir)
            output_dir.mkdir(exist_ok=True, parents=True)
            
            output_file = output_dir / f"{path.stem}_result.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                if result["vlm_result"]:
                    f.write(f"VLM结果:\n{result['vlm_result']}\n\n")
                f.write(f"OCR结果:\n{result['ocr_result']}")
            
            print(f"结果已保存到: {output_file}")
    else:
        print(f"不支持的文件类型: {path.suffix}")


if __name__ == "__main__":
    main()
