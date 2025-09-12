"""简化版测试脚本，测试增强后的分块器对加粗行的识别效果。"""

import re
import uuid
from typing import List, Dict, Any, Optional, Tuple

# 简化版的Chunk类，仅用于测试
class SimpleChunk:
    def __init__(self, chunk_id: str, text: str, metadata: Dict[str, Any]):
        self.chunk_id = chunk_id
        self.text = text
        self.metadata = metadata

# 简化版的分块器，仅包含我们修改的部分
class SimpleBoldHeaderChunker:
    def __init__(self, source_filename: str = "test.md"):
        self.source_filename = source_filename
    
    def chunk(self, markdown_content: str) -> List[SimpleChunk]:
        """简化版的分块方法，仅处理二级标题和加粗行。"""
        # 先按二级标题分块
        sections = self._split_sections(markdown_content, 2)
        if not sections:
            return []
        
        all_chunks = []
        
        for header, body in sections:
            # 创建二级标题块
            header_chunk_id = str(uuid.uuid4())
            header_chain = [header]
            
            header_chunk = SimpleChunk(
                chunk_id=header_chunk_id,
                text=f"## {header}",
                metadata=self._create_metadata(None, header_chain)
            )
            
            all_chunks.append(header_chunk)
            
            # 处理加粗行作为子标题
            bold_chunks = self._extract_bold_headers_as_chunks(
                body, header_chunk_id, header_chain)
            
            if bold_chunks:
                all_chunks.extend(bold_chunks)
                # 如果找到了加粗行子标题，从主标题块中移除文本
                header_chunk.text = f"## {header}"
            else:
                # 如果没有加粗行，将文本合并到标题块
                header_chunk.text += f"\n{body}"
        
        return all_chunks
    
    def _extract_bold_headers_as_chunks(
        self, text: str, parent_id: str, header_chain: List[str]
    ) -> List[SimpleChunk]:
        """从文本中提取加粗行作为子标题，并创建对应的块。"""
        # 匹配加粗行模式：如 "**功能：**" 或 "**本地实现方案：**"
        bold_header_pattern = re.compile(r"^\*\*([^\*]+)\*\*", re.MULTILINE)
        matches = list(bold_header_pattern.finditer(text))
        
        if not matches:
            return []
            
        # 将文本按加粗行分割成多个部分
        sections = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            header = match.group(1).strip()  # 去除星号得到纯文本
            body = text[match.end():end].strip()
            sections.append((header, body))
        
        # 创建块
        bold_chunks = []
        for header, body in sections:
            # 去除可能的尾随冒号或其他标点
            clean_header = re.sub(r'[\:：]\s*$', '', header)
            
            # 创建子标题块
            chunk_id = str(uuid.uuid4())
            current_header_chain = header_chain + [clean_header]
            
            chunk = SimpleChunk(
                chunk_id=chunk_id,
                text=f"**{clean_header}**\n{body}",
                metadata=self._create_metadata(parent_id, current_header_chain)
            )
            bold_chunks.append(chunk)
        
        # 设置兄弟关系
        sibling_ids = [c.chunk_id for c in bold_chunks]
        for c in bold_chunks:
            c.metadata["sibling_ids"] = [sid for sid in sibling_ids if sid != c.chunk_id]
            
        return bold_chunks
    
    def _create_metadata(
        self, parent_id: str | None = None, header_chain: List[str] | None = None
    ) -> dict:
        return {
            "parent_id": parent_id,
            "source_filename": self.source_filename,
            "header_chain": header_chain or [],
            "sibling_ids": [],
        }
    
    def _split_sections(self, content: str, level: int) -> List[Tuple[str, str]]:
        """按指定级别的标题分割内容。"""
        pattern = re.compile(rf"^{'#'*level} (.+)", re.MULTILINE)
        matches = list(pattern.finditer(content))
        if not matches:
            return []
        sections = []
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            header = match.group(1).strip()
            body = content[start:end].strip()
            sections.append((header, body))
        return sections


def print_chunk_tree(chunks):
    """打印块的树状结构，方便查看层级关系。"""
    # 构建父子关系图
    parent_to_children = {}
    id_to_chunk = {}
    roots = []
    
    for chunk in chunks:
        id_to_chunk[chunk.chunk_id] = chunk
        parent_id = chunk.metadata.get("parent_id")
        if parent_id:
            if parent_id not in parent_to_children:
                parent_to_children[parent_id] = []
            parent_to_children[parent_id].append(chunk)
        else:
            roots.append(chunk)
    
    # 递归打印树
    def _print_tree(chunk, level=0):
        indent_str = "  " * level
        header_chain = " > ".join(chunk.metadata.get("header_chain", []))
        first_line = chunk.text.split("\n")[0]
        print(f"{indent_str}- [{chunk.chunk_id[:8]}] {first_line}")
        print(f"{indent_str}  header_chain: {header_chain}")
        
        # 打印子节点
        children = parent_to_children.get(chunk.chunk_id, [])
        for child in children:
            _print_tree(child, level + 1)
    
    # 打印所有根节点
    for root in roots:
        _print_tree(root)


def test_bold_headers_chunking():
    """测试分块器对加粗行的识别。"""
    # 创建一个测试用的Markdown文本，包含二级标题和加粗行作为子标题
    test_markdown = """# 测试文档

## 第一章 基础知识

这是第一章的介绍内容。

**概念定义：** 这里是一些基本概念的定义。
这是概念定义的详细内容。

**重要原则：** 以下是一些重要原则。
- 原则1
- 原则2

## 第二章 高级应用

这是第二章的介绍内容。

**应用场景：** 这里描述了一些应用场景。
场景1...
场景2...

**最佳实践：** 以下是一些最佳实践。
实践1...
实践2...
"""

    # 使用分块器处理测试文本
    chunker = SimpleBoldHeaderChunker(source_filename="test_markdown.md")
    chunks = chunker.chunk(test_markdown)
    
    # 打印结果
    print(f"\n找到 {len(chunks)} 个块:")
    print_chunk_tree(chunks)
    
    # 验证结果
    # 1. 应该有2个根节点（二级标题）
    # 2. 每个根节点下应该有2个子节点（加粗行）
    roots = [c for c in chunks if not c.metadata.get("parent_id")]
    assert len(roots) == 2, f"应该有2个根节点，但找到了 {len(roots)} 个"
    
    # 检查每个根节点的子节点
    for root in roots:
        children = [c for c in chunks if c.metadata.get("parent_id") == root.chunk_id]
        assert len(children) == 2, f"根节点 {root.chunk_id} 应该有2个子节点，但找到了 {len(children)} 个"
        
        # 检查子节点的header_chain
        for child in children:
            assert len(child.metadata["header_chain"]) == 2, f"子节点的header_chain长度应该为2，但是 {len(child.metadata['header_chain'])}"
            assert child.metadata["header_chain"][0] in ["第一章 基础知识", "第二章 高级应用"], "子节点的header_chain[0]应该是父标题"
    
    print("\n所有测试通过！")
    return chunks


if __name__ == "__main__":
    chunks = test_bold_headers_chunking()
