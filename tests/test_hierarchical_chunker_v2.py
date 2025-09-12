"""测试 HierarchicalChunkerV2 对加粗行的识别效果。"""

import sys
import os
from pathlib import Path

# 确保项目根目录在sys.path中
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.forma.shared.chunker_v2 import HierarchicalChunkerV2


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


def test_with_real_document():
    """使用实际文档测试 HierarchicalChunkerV2。"""
    # 创建一个测试用的Markdown文本，模拟实际文档中的二级标题和加粗行
    test_markdown = """# AI 短视频工厂项目可行性与技术方案研究

## 项目概述和目标

**项目简介：** "AI 短视频工厂"旨在将视频素材自动化加工为全新的短视频内容，并实现多渠道投放的闭环优化。项目分为四个阶段： (1) **素材抽取流水线** – 从原始视频自动提取可用素材（切分片段、去除字幕、语音转写、文本处理等）； (2) **AI 学习与内容创作** – 根据用户提供的主题，利用 AI 生成视频脚本（包括角色、分镜、解说词、节奏），并从素材库匹配相应画面； (3) **视频合成与后处理** – 将选定片段与 AI 生成的语音、音乐、转场效果、文本动画等合成新的成品视频； (4) **多渠道投放与 AB 测试** – 将视频发布到各平台并收集反馈，实现内容优化的循环。

**技术要求与挑战：** 当前 MVP 在本地 GPU 上验证各模块可行性，未来部署可能无法依赖 GPU，因此每个模块需有**多种实现方案** （本地/云端）以确保在不同硬件环境下均可运行。内容创作阶段需要支持 **可插拔的 LLM 提供商** ，不能局限于单一厂商（如谷歌 LLM），建议使用 LangChain 框架以便灵活切换模型和组合多步骤的 AI 生成流程。整体方案需专业可行、易于维护，充分利用成熟的工具和服务来降低开发难度。下面我们将按照各阶段模块详细分析可行的技术方案，并评估本地方案与云端方案的选择。

## 素材抽取流水线

**视频切分（镜头/语义）**
**功能：** 将原始视频按内容切分成若干"素材片段"，便于后续处理和重组。基本要求是检测镜头切换点（shot boundary）；进一步可按语义将连续镜头归为一段场景。

**本地实现方案：** 推荐使用开源的 **PySceneDetect** 库实现镜头切分。PySceneDetect 提供多种镜头过渡检测算法（硬切、淡入淡出等）。该工具无需 GPU，在 CPU 上通过像素变化阈值就能高效检测出视频中的镜头边界，并可自动输出逐段剪切的视频片段。例如，PySceneDetect 的 ContentDetector 和 ThresholdDetector适合不同场景下的镜头检测，满足 MVP 需求。对于 **语义分段** （跨镜头的场景单元），可在镜头切分结果基础上，通过比较相邻片段的视觉特征或文本内容进行归并。例如提取每段的图像特征（关键帧嵌入）或 ASR 转录的主题词，以判断多段是否属于同一情境，然后合并。初期可以不做复杂的语义合并，先以镜头切分为主实现MVP。

**云端实现方案：** 利用云服务的视听分析 API。 **Google Cloud Video Intelligence API** 提供开箱即用的镜头边界检测功能，只需上传视频即可返回所有镜头切换时间点。类似地， **AWS Rekognition Video** 提供"段检测(Segment Detection)"接口，可识别视频中的镜头切换以及黑场等技术片段。云方案的优点是准确且省去本地处理负担，但需上传视频（带宽耗时、数据隐私）且按时长计费。若视频较长或数量多，本地PySceneDetect 可能更经济。两者都可在提取镜头基础上，辅以简单规则或云端返回的 **内容标签** 实现语义分段（如 Google 的 API 同时可返回每段的场景标签，有助于语义归类）。"""

    # 使用 HierarchicalChunkerV2 处理测试文本
    chunker = HierarchicalChunkerV2(source_filename="test_real_document.md")
    chunks = chunker.chunk(test_markdown)
    
    # 打印结果
    print(f"\n找到 {len(chunks)} 个块:")
    print_chunk_tree(chunks)
    
    # 验证结果
    # 1. 应该有2个根节点（二级标题）
    # 2. 每个根节点下应该有子节点（加粗行）
    roots = [c for c in chunks if not c.metadata.get("parent_id")]
    assert len(roots) >= 2, f"应该有至少2个根节点，但找到了 {len(roots)} 个"
    
    # 检查每个根节点的子节点
    for root in roots:
        children = [c for c in chunks if c.metadata.get("parent_id") == root.chunk_id]
        assert len(children) > 0, f"根节点 {root.chunk_id} 应该有子节点，但找到了 {len(children)} 个"
        
        # 检查子节点的header_chain
        for child in children:
            assert len(child.metadata["header_chain"]) > 1, f"子节点的header_chain长度应该大于1，但是 {len(child.metadata['header_chain'])}"
            assert child.metadata["header_chain"][0] in ["项目概述和目标", "素材抽取流水线"], "子节点的header_chain[0]应该是父标题"
    
    print("\n所有测试通过！")
    return chunks


if __name__ == "__main__":
    chunks = test_with_real_document()
