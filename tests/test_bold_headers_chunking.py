"""测试增强后的分块器对加粗行的识别效果。"""

import sys
import os
from pathlib import Path

# 确保项目根目录在sys.path中
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.forma.shared.chunker import HierarchicalChunker
from src.forma.shared.models import Chunk


def print_chunk_tree(chunks, indent=0):
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
    chunker = HierarchicalChunker(source_filename="test_markdown.md")
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
