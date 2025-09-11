#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCR演示程序：展示如何使用阿里云文字识别OCR服务
"""

import os
import sys
import requests
import json
from pathlib import Path
from PIL import Image
import base64
import io


def image_to_base64(image_path):
    """将图片转换为base64编码"""
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_string


def call_ocr_api(image_path, api_key=None):
    """
    调用阿里云OCR API

    Args:
        image_path: 图片路径
        api_key: API密钥，如果为None则从环境变量获取

    Returns:
        识别结果文本
    """
    # 从环境变量获取API密钥（优先使用参数，其次环境变量）
    api_key = "INIWTYCGQPBFETSHHIZBLQJWOHBDPP6ZEBATA54G"

    # API端点（参考文档）
    url = "https://ai.gitee.com/v1/images/ocr"

    # 按文档要求使用表单提交与 multipart 文件上传
    data = {
        "model": "GOT-OCR2_0",
    }

    # 发送请求（multipart/form-data），不手动设置 Content-Type，由 requests 自动处理
    print(f"正在处理图片: {Path(image_path).name}")
    with open(image_path, "rb") as f:
        files = {
            # 字段名为 image；文件名与内容一起上传
            "image": (Path(image_path).name, f, "application/octet-stream"),
        }
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        response = requests.post(url, headers=headers, data=data, files=files, timeout=60)

    # 处理响应
    if response.status_code == 200:
        result = response.json()
        # 参考示例：返回 {"text": "Hello"}
        if isinstance(result, dict) and "text" in result:
            return result["text"]
        print(f"API返回了意外的响应格式: {result}")
        return None
    else:
        print(f"API请求失败，状态码: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def process_image_directory(directory_path):
    """处理目录中的所有图片"""
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']
    results = {}

    directory = Path(directory_path)
    if not directory.exists():
        print(f"目录不存在: {directory_path}")
        return results

    for file_path in directory.iterdir():
        if file_path.suffix.lower() in image_extensions:
            result = call_ocr_api(str(file_path))
            if result:
                results[file_path.name] = result
                print(f"成功识别 {file_path.name}")
                print(f"识别结果: {result[:100]}..." if len(
                    result) > 100 else f"识别结果: {result}")
                print("-" * 50)

    return results


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="OCR图片识别演示程序")
    parser.add_argument("path", help="图片路径或包含图片的目录路径")
    parser.add_argument("--api-key", help="OCR API密钥，如不提供则从环境变量OCR_API_KEY获取")
    parser.add_argument("--output", help="输出结果的文件路径")

    args = parser.parse_args()

    path = Path(args.path)

    if path.is_file():
        # 处理单个文件
        result = call_ocr_api(str(path), args.api_key)
        if result:
            print(f"识别结果: {result}")
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(result)
                print(f"结果已保存到: {args.output}")
    elif path.is_dir():
        # 处理目录
        results = process_image_directory(str(path))
        if results and args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"结果已保存到: {args.output}")
    else:
        print(f"路径无效: {args.path}")


if __name__ == "__main__":
    main()
