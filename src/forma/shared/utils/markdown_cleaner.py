"""Markdown cleaner module for cleaning and formatting markdown content."""

import re
from typing import List, Pattern


class MarkdownCleaner:
    """Cleans and formats markdown content for better readability."""

    @staticmethod
    def clean_markdown(content: str) -> str:
        """
        Clean markdown content by:
        1. Removing excessive empty lines (keeping only one)
        2. Removing empty sections between horizontal rules
        3. Normalizing spacing around headers, lists, and code blocks
        
        Parameters
        ----------
        content : str
            The markdown content to clean
            
        Returns
        -------
        str
            The cleaned markdown content
        """
        if not content:
            return content
            
        # 步骤1: 删除多余的空行，只保留一个空行
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # 步骤2: 删除没有内容的分隔符段落
        # 匹配连续的分隔符（---）之间没有实际内容的情况
        content = re.sub(r'---\s*\n\s*---', '---', content)
        
        # 步骤3: 删除连续的分隔符
        # 这会处理多个连续的分隔符的情况
        pattern = re.compile(r'(---\s*\n)+---')
        while pattern.search(content):
            content = pattern.sub('---', content)
        
        # 步骤4: 确保分隔符前后有空行
        content = re.sub(r'([^\n])(\n---)', r'\1\n\n---', content)
        content = re.sub(r'(---\n)([^\n])', r'---\n\n\2', content)
        
        # 步骤5: 规范化标题前后的空行
        content = re.sub(r'\n{2,}(#+\s)', r'\n\n\1', content)
        content = re.sub(r'(#+\s.*)\n{2,}', r'\1\n\n', content)
        
        # 步骤6: 删除文档开头的空行
        content = re.sub(r'^\s*\n', '', content)
        
        # 步骤7: 删除文档末尾的空行
        content = re.sub(r'\n\s*$', '\n', content)
        
        return content
