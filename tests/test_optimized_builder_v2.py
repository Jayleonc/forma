#!/usr/bin/env python3
"""Test script for the optimized HierarchicalKnowledgeBuilder v2."""

import time
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from forma.shared.chunker_v2 import HierarchicalChunkerV2
from forma.qa.builder_v2 import HierarchicalKnowledgeBuilder


def test_optimized_builder():
    """Test the optimized builder with a sample document."""
    
    # Sample markdown content with hierarchical structure
    sample_content = """
# AI短视频工厂项目可行性与技术方案研究

## 1. 项目概述

### 1.1 项目背景
随着短视频平台的快速发展，内容创作需求激增。AI技术的成熟为自动化内容生产提供了可能性。

### 1.2 项目目标
构建一个基于AI的短视频自动生成平台，实现从文本到视频的全流程自动化。

## 2. 技术架构

### 2.1 核心技术栈
- 自然语言处理：GPT系列模型
- 计算机视觉：Stable Diffusion, DALL-E
- 语音合成：ElevenLabs, Azure Speech
- 视频编辑：FFmpeg, OpenCV

### 2.2 系统架构
采用微服务架构，包含以下核心服务：
- 内容分析服务
- 素材生成服务
- 视频合成服务
- 用户管理服务

## 3. 实施方案

### 3.1 第一阶段：MVP开发
开发基础的文本到视频转换功能，支持简单的模板化生成。

### 3.2 第二阶段：功能增强
增加个性化定制、批量处理、高级编辑功能。

### 3.3 第三阶段：商业化
完善用户体验，接入支付系统，开展商业运营。

## 4. 风险评估

### 4.1 技术风险
- AI模型的稳定性和准确性
- 大规模并发处理能力
- 版权和合规问题

### 4.2 市场风险
- 竞争对手的技术迭代
- 用户接受度和付费意愿
- 监管政策变化

## 5. 结论

基于当前技术发展趋势和市场需求分析，AI短视频工厂项目具有较好的可行性。
建议采用分阶段实施策略，先验证核心技术方案，再逐步扩展功能和商业化。
"""

    print("=" * 60)
    print("测试优化后的 HierarchicalKnowledgeBuilder v2")
    print("=" * 60)
    
    # 第一步：分块处理
    print("\n[阶段1] 文档分块处理...")
    chunker = HierarchicalChunkerV2(source_filename="test_document.md")
    chunks = chunker.chunk(sample_content)
    print(f"生成了 {len(chunks)} 个文本块")
    
    # 显示块的层级结构
    print("\n文档层级结构：")
    for i, chunk in enumerate(chunks[:10]):  # 只显示前10个
        header_chain = " > ".join(chunk.metadata.get("header_chain", []))
        parent_id = chunk.metadata.get("parent_id", "无")
        print(f"  块{i+1}: {chunk.chunk_id[:8]}... | 父级: {parent_id[:8] if parent_id != '无' else '无'} | 路径: {header_chain}")
    
    if len(chunks) > 10:
        print(f"  ... 还有 {len(chunks) - 10} 个块")
    
    # 第二步：测试优化后的知识构建
    print(f"\n[阶段2] 优化后的知识构建测试...")
    
    # 创建优化后的构建器
    builder = HierarchicalKnowledgeBuilder(
        max_workers=4,  # 并行处理线程数
        similarity_threshold=0.6,  # 降低相似度阈值以便测试
    )
    
    # 记录开始时间
    start_time = time.time()
    
    # 执行知识构建
    authoritative_units = builder.build(
        chunks=chunks,
        skip_global_synthesis=False,  # 测试完整流程
        batch_size=20
    )
    
    # 记录结束时间
    end_time = time.time()
    total_time = end_time - start_time
    
    print(f"\n[结果] 知识构建完成！")
    print(f"总耗时: {total_time:.2f} 秒")
    print(f"生成了 {len(authoritative_units)} 个权威知识单元")
    
    # 显示结果摘要
    print(f"\n权威知识单元摘要：")
    total_qa_pairs = 0
    for i, unit in enumerate(authoritative_units):
        qa_count = len(unit.qa_pairs)
        total_qa_pairs += qa_count
        source_count = len(unit.source_chunks)
        print(f"  {i+1}. {unit.category}: {qa_count} 个QA对, 来源于 {source_count} 个块")
        
        # 显示前2个QA对作为示例
        for j, qa in enumerate(unit.qa_pairs[:2]):
            print(f"     Q{j+1}: {qa['question'][:50]}...")
            print(f"     A{j+1}: {qa['answer'][:50]}...")
    
    print(f"\n总计生成 {total_qa_pairs} 个QA对")
    
    # 性能分析
    print(f"\n[性能分析]")
    print(f"平均每个块处理时间: {total_time / len(chunks):.3f} 秒")
    print(f"平均每个QA对生成时间: {total_time / max(total_qa_pairs, 1):.3f} 秒")
    
    return authoritative_units


def test_skip_global_synthesis():
    """测试跳过全局整合的模式。"""
    print("\n" + "=" * 60)
    print("测试跳过全局整合模式")
    print("=" * 60)
    
    # 简单的测试内容
    simple_content = """
# 测试文档

## 第一章：基础概念
Python是一种高级编程语言，具有简洁的语法和强大的功能。

## 第二章：数据类型
Python支持多种数据类型，包括整数、浮点数、字符串和列表。

### 2.1 数字类型
整数和浮点数是Python中的基本数字类型。

### 2.2 字符串类型
字符串用于表示文本数据，可以使用单引号或双引号定义。
"""
    
    # 分块
    chunker = HierarchicalChunkerV2(source_filename="simple_test.md")
    chunks = chunker.chunk(simple_content)
    print(f"生成了 {len(chunks)} 个文本块")
    
    # 测试跳过全局整合
    builder = HierarchicalKnowledgeBuilder(max_workers=2)
    
    start_time = time.time()
    qa_pairs = builder.build(
        chunks=chunks,
        skip_global_synthesis=True  # 跳过第二阶段
    )
    end_time = time.time()
    
    print(f"跳过全局整合模式耗时: {end_time - start_time:.2f} 秒")
    print(f"生成了 {len(qa_pairs)} 个原始QA对")
    
    # 显示前几个QA对
    for i, qa in enumerate(qa_pairs[:3]):
        print(f"  Q{i+1}: {qa['question']}")
        print(f"  A{i+1}: {qa['answer'][:100]}...")
        print(f"  来源: {qa['source_chunk'][:8]}... | 路径: {qa['header_chain']}")
        print()
    
    return qa_pairs


if __name__ == "__main__":
    try:
        # 测试完整流程
        units = test_optimized_builder()
        
        # 测试跳过全局整合
        qa_pairs = test_skip_global_synthesis()
        
        print("\n" + "=" * 60)
        print("所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
