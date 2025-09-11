#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
高级OCR演示程序：展示如何使用GOT-OCR2_0进行文字识别
"""

import os
import sys
import argparse
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.forma.ocr import ocr_image_file, AdvancedOCRClient
from src.forma.shared.config import get_ocr_config


def process_image_with_ocr(image_path):
    """
    使用原有OCR处理图片
    
    Args:
        image_path: 图片路径
    
    Returns:
        OCR结果文本
    """
    print(f"使用原有OCR处理图片: {Path(image_path).name}")
    try:
        result = ocr_image_file(image_path)
        print(f"OCR结果 ({len(result)} 字符):")
        print("-" * 40)
        print(result)
        print("-" * 40)
        return result
    except Exception as e:
        print(f"OCR处理失败: {e}")
        return ""


def process_image_with_advanced_ocr(image_path):
    """
    使用高级OCR（GOT-OCR2_0）处理图片
    
    Args:
        image_path: 图片路径
    
    Returns:
        高级OCR结果文本
    """
    print(f"使用高级OCR（GOT-OCR2_0）处理图片: {Path(image_path).name}")
    
    try:
        # 创建高级OCR客户端
        config = get_ocr_config()
        client = AdvancedOCRClient(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
            max_file_size=config.max_file_size
        )
        
        # 获取文件大小
        file_size = os.path.getsize(image_path)
        print(f"文件大小: {file_size} 字节")
        
        # 处理图片
        result = client.recognize_text(image_path)
        print(f"高级OCR结果 ({len(result)} 字符):")
        print("-" * 40)
        print(result)
        print("-" * 40)
        return result
    except ValueError as e:
        print(f"高级OCR处理失败 (值错误): {e}")
        return ""
    except Exception as e:
        print(f"高级OCR处理失败: {e}")
        return ""


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="高级OCR演示程序")
    parser.add_argument("image_path", help="要处理的图片路径")
    parser.add_argument("--output", help="输出结果的文件路径")
    parser.add_argument("--compare", action="store_true", help="比较原有OCR和高级OCR的结果")
    
    args = parser.parse_args()
    
    # 检查图片是否存在
    image_path = Path(args.image_path)
    if not image_path.exists():
        print(f"错误: 图片不存在: {image_path}")
        return
    
    results = {}
    
    # 使用原有OCR处理
    if args.compare:
        results["原有OCR"] = process_image_with_ocr(args.image_path)
    
    # 使用高级OCR处理
    results["高级OCR"] = process_image_with_advanced_ocr(args.image_path)
    
    # 保存结果
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            for name, result in results.items():
                f.write(f"=== {name} ===\n\n")
                f.write(result)
                f.write("\n\n")
        print(f"结果已保存到: {args.output}")


if __name__ == "__main__":
    main()
