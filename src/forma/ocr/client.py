#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCR客户端类，用于处理GOT-OCR2_0请求
"""

import os
import requests
from pathlib import Path
from typing import Optional, Dict, Any, Union
import logging

logger = logging.getLogger(__name__)

class AdvancedOCRClient:
    """高级OCR客户端，用于调用GOT-OCR2_0等外部API进行图片文字识别"""

    def __init__(
        self,
        api_key: str,
        model: str = "GOT-OCR2_0",
        base_url: Optional[str] = None,
        max_file_size: int = 3 * 1024 * 1024  # 默认3MB
    ):
        """
        初始化OCR客户端
        
        Args:
            api_key: API密钥
            model: OCR模型名称，默认为GOT-OCR2_0
            base_url: API基础URL，默认为https://ai.gitee.com
            max_file_size: 最大文件大小（字节），默认为3MB
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://ai.gitee.com"
        self.max_file_size = max_file_size
        
    def recognize(self, image_path: Union[str, Path]) -> Dict[str, Any]:
        """
        识别图片中的文字
        
        Args:
            image_path: 图片路径
            
        Returns:
            识别结果字典
            
        Raises:
            ValueError: 如果文件不存在或大小超过限制
            RuntimeError: 如果API调用失败
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise ValueError(f"文件不存在: {image_path}")
        
        # 检查文件大小
        file_size = image_path.stat().st_size
        if file_size > self.max_file_size:
            raise ValueError(f"文件大小({file_size}字节)超过限制({self.max_file_size}字节)")
        
        # 构建API请求
        url = f"{self.base_url}/v1/images/ocr"
        
        # 按文档要求使用表单提交与multipart文件上传
        data = {
            "model": self.model,
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            with open(image_path, "rb") as f:
                files = {
                    "image": (image_path.name, f, "application/octet-stream")
                }
                response = requests.post(
                    url, 
                    headers=headers, 
                    data=data, 
                    files=files,
                    timeout=60
                )
        except Exception as e:
            logger.error(f"OCR请求失败: {e}")
            raise RuntimeError(f"OCR请求失败: {e}")
        
        # 处理响应
        if response.status_code == 200:
            return response.json()
        else:
            error_msg = f"OCR API调用失败，状态码: {response.status_code}, 错误信息: {response.text}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def recognize_text(self, image_path: Union[str, Path]) -> str:
        """
        识别图片中的文字并返回文本
        
        Args:
            image_path: 图片路径
            
        Returns:
            识别的文本内容
            
        Raises:
            ValueError: 如果文件不存在或大小超过限制
            RuntimeError: 如果API调用失败或返回格式不正确
        """
        try:
            result = self.recognize(image_path)
            if "text" in result:
                return result["text"]
            else:
                logger.warning(f"OCR返回了意外的响应格式: {result}")
                return ""
        except ValueError as e:
            # 文件不存在或大小超过限制，直接抛出
            raise
        except Exception as e:
            # 其他错误，包装为RuntimeError
            raise RuntimeError(f"OCR文本识别失败: {e}")
