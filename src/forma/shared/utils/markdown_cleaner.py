"""Markdown cleaner module for cleaning and formatting markdown content."""

import re
from typing import List, Pattern


class MarkdownCleaner:
    """Cleans and formats markdown content for better readability."""

    @staticmethod
    def normalize_inline_markdown(content: str) -> str:
        """
        Normalize inline markdown content with basic sanitization:
        1. Ensure UTF-8 encoding
        2. Normalize line endings to Unix style (\n)
        3. Remove null characters
        4. Strip trailing whitespace from lines
        5. Ensure single trailing newline

        Parameters
        ----------
        content : str
            The markdown content to normalize

        Returns
        -------
        str
            The normalized markdown content
        """
        if not content:
            return content

        # Remove null characters
        content = content.replace('\x00', '')

        # Normalize line endings to Unix style
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Strip trailing whitespace from each line
        lines = content.splitlines()
        lines = [line.rstrip() for line in lines]
        content = '\n'.join(lines)

        # Ensure single trailing newline
        content = content.rstrip() + '\n' if content else ''

        return content

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
        # 先将所有可能的带空格的---统一为---
        content = re.sub(r'---\s*\n', '---\n', content)
        # 用简单的循环替换来处理连续的分隔符
        while '---\n---' in content:
            content = content.replace('---\n---', '---')

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

        # 步骤8: 清理文末连续的图片描述（image desc）块
        # 如果文档末尾仅包含若干行形如 "> **image desc N**: ..." 的描述，将这些尾部块整体去除
        lines = content.splitlines()
        trailing_desc_pattern = re.compile(
            r'^\s*> \*\*image desc\s+\d+\*\*:', re.IGNORECASE)

        # 从后向前遍历，找到第一个不是图片描述的行
        last_content_line_index = -1
        for i in range(len(lines) - 1, -1, -1):
            if not trailing_desc_pattern.match(lines[i]):
                last_content_line_index = i
                break

        # 如果找到了非描述行，就切片保留之前的内容；否则说明全是描述，清空
        if last_content_line_index != -1:
            content = "\n".join(lines[:last_content_line_index + 1])
        else:
            content = ""

        # 恢复可能存在的文末换行符
        if content:
            content += "\n"

        # 步骤9: 移除无信息量的图片描述行（过短/噪声）
        def _filter_line(line: str) -> str:
            m = re.match(r'^(\s*> \*\*image desc\s+\d+\*\*:\s*)(.*)$',
                         line, flags=re.IGNORECASE)
            if not m:
                return line
            desc = m.group(2).strip()
            # 过短的内容直接移除，例如只有 1-4 个字符（如 "-", "1", "ME" 等）
            if len(desc) < 5:
                return ''
            return line
        lines = content.splitlines()
        lines = [ln for ln in (_filter_line(ln) for ln in lines) if ln != '']
        content = "\n".join(lines) + ("\n" if content.endswith("\n") else "")

        return content
