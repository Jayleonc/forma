#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
阿里云OCR API演示程序
基于图片中展示的API调用方式
"""

import requests
import argparse
import base64
from pathlib import Path
import json
import os

def image_to_base64(image_path):
    """将图片转换为base64编码"""
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_string

def call_aliyun_ocr(image_path, api_key=None):
    """
    调用阿里云OCR API
    
    Args:
        image_path: 图片路径
        api_key: API密钥，如果为None则从环境变量获取
    
    Returns:
        API响应
    """
    # 从环境变量获取API密钥
    api_key = api_key or os.environ.get("ALIYUN_OCR_API_KEY")
    if not api_key:
        raise ValueError("API密钥未提供，请设置ALIYUN_OCR_API_KEY环境变量或通过--api-key参数提供")
    
    # API端点
    url = "https://ai.gitee.com/v1/images/ocr"
    
    # 准备请求数据
    image_base64 = image_to_base64(image_path)
    payload = {
        "model": "GOT-OCR2_0",
        "image": image_base64
    }
    
    # 设置请求头
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # 发送请求
    print(f"正在调用阿里云OCR API处理图片: {Path(image_path).name}")
    response = requests.post(url, headers=headers, json=payload)
    
    return response

def main():
    parser = argparse.ArgumentParser(description="阿里云OCR API演示程序")
    parser.add_argument("image_path", help="要处理的图片路径")
    parser.add_argument("--api-key", help="阿里云OCR API密钥")
    parser.add_argument("--output", help="输出结果的JSON文件路径")
    
    args = parser.parse_args()
    
    # 检查图片是否存在
    image_path = Path(args.image_path)
    if not image_path.exists():
        print(f"错误: 图片不存在: {image_path}")
        return
    
    try:
        # 调用API
        response = call_aliyun_ocr(str(image_path), args.api_key)
        
        # 处理响应
        if response.status_code == 200:
            result = response.json()
            print("API调用成功!")
            print("识别结果:")
            print("-" * 50)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            
            # 保存结果
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"结果已保存到: {args.output}")
        else:
            print(f"API调用失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
    
    except Exception as e:
        print(f"处理过程中出错: {e}")

if __name__ == "__main__":
    main()
