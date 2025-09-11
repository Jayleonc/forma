"""Knowledge building workflow utilities for hierarchical processing."""

from __future__ import annotations

from typing import Any, Dict, List, DefaultDict, Set, Tuple
from collections import defaultdict
import json
import time
import concurrent.futures
from functools import partial

from langchain.output_parsers import PydanticOutputParser, OutputFixingParser
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..shared.config import get_llm_config
from ..shared.prompts import PromptManager
from ..shared.models import (
    Chunk,
    DistilledKnowledge,
    EnrichedChunk,
    AuthoritativeKnowledgeUnit,
    AuthoritativeKnowledgeList,
)


class HierarchicalKnowledgeBuilder:
    """封装带有摘要回填的层级化知识构建工作流。"""

    def __init__(
        self,
        prompt_manager: PromptManager | None = None,
        client: ChatOpenAI | None = None,
        max_workers: int = 4,  # 默认并行处理线程数
        chunk_max_length: int = 50000,  # 单次处理的最大文本长度
        parent_summary_max_length: int = 1000,  # 父级摘要最大长度
        header_chain_max_length: int = 500,  # 层级路径最大长度
    ) -> None:
        cfg = get_llm_config()
        # Initialize LLM client with deterministic, JSON-enforcing settings
        self.client = client or ChatOpenAI(
            model=cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        self.prompt_manager = prompt_manager or PromptManager()
        self.max_workers = max_workers
        self.chunk_max_length = chunk_max_length
        self.parent_summary_max_length = parent_summary_max_length
        self.header_chain_max_length = header_chain_max_length
        self.start_time = time.time()

    def _invoke(self, prompt: Dict[str, Any]) -> str:
        messages = []
        system_prompt = prompt.get("system")
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt.get("user", "")))
        result = self.client.invoke(messages)
        return getattr(result, "content", "") or ""

    def _distill_chunk_with_context(
        self, chunk: Chunk, parent_summary: str
    ) -> EnrichedChunk:
        """在层级上下文中处理单个文本块。

        根据节点是否有父节点，动态选择并填充适当的Prompt。
        对于有父节点的块，将父节点的摘要注入到Prompt中。

        Args:
            chunk: 待处理的文本块
            parent_summary: 父节点的摘要，如果是根节点则为空字符串

        Returns:
            包含知识提炼结果的 EnrichedChunk
        """
        # 始终使用层级化知识提炼的Prompt
        template = self.prompt_manager.get_prompt(
            "hierarchical_knowledge_distillation_prompt"
        )

        # 准备解析器
        base_parser = PydanticOutputParser(pydantic_object=DistilledKnowledge)
        fixing_parser = OutputFixingParser.from_llm(
            llm=self.client, parser=base_parser
        )

        # 创建提示模板
        prompt_template = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=template.get("system", "")),
                HumanMessagePromptTemplate.from_template(
                    template.get("user", "") + "\n{format_instructions}"
                ),
            ]
        )
        chain = prompt_template | self.client | fixing_parser

        # 准备层级路径信息（限制长度，避免过长上下文拖慢调用）
        header_chain = " > ".join(chunk.metadata.get("header_chain", []))[
            :self.header_chain_max_length]

        # 语言偏好：根据原文主要语言决定输出语言，混杂时优先中文
        def _detect_language_hint(text: str) -> str:
            # 简单启发式：统计中文字符占比
            if not text:
                return "请使用中文输出。"
            chinese_chars = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
            ratio = chinese_chars / max(len(text), 1)
            if ratio >= 0.2:  # 含有明显中文
                return "请使用中文进行摘要与问答。"
            return "Please respond in English."

        preferred_language_instruction = _detect_language_hint(chunk.text)

        # 处理父级摘要信息（限制长度，避免上下文过长）
        if not parent_summary:
            # 如果是根节点，提供一个默认提示
            parent_summary = "这是一个顶级章节，没有父级内容。"
            print(f"[DEBUG] 节点 {chunk.chunk_id} 是根节点，使用默认父级摘要")
        else:
            parent_summary = parent_summary[:self.parent_summary_max_length]
            print(
                f"[DEBUG] 节点 {chunk.chunk_id} 使用父级摘要: {parent_summary[:50]}...")

        # 若文本过短/几乎为空，直接返回最小占位知识，避免模型产生占位说明或解析错误
        plain_text = (chunk.text or "").strip()
        if len(plain_text) < 20:
            minimal_summary = header_chain.split(
                " > ")[-1] if header_chain else plain_text
            print(
                f"[INFO] 节点 {chunk.chunk_id} 文本过短（{len(plain_text)} 字），跳过LLM调用，返回最小知识占位")
            knowledge = DistilledKnowledge(
                summary=minimal_summary,
                qa_pairs=[],
                hypothetical_questions=[],
                entities={},
            )
            return EnrichedChunk(**chunk.model_dump(), knowledge=knowledge)

        try:
            # 调用大模型提炼知识，注入层级路径和父级摘要
            print(f"[INFO] 开始处理节点 {chunk.chunk_id}")
            # 限制单次调用的文本长度，兼顾速度与信息密度
            truncated_text = plain_text[:self.chunk_max_length]
            response = chain.invoke(
                {
                    "chunk_text": truncated_text,
                    "header_chain": header_chain,
                    "parent_summary": parent_summary,
                    "preferred_language_instruction": preferred_language_instruction,
                    "format_instructions": base_parser.get_format_instructions(),
                }
            )

            # 处理响应结果
            if isinstance(response, DistilledKnowledge):
                knowledge = response
                print(
                    f"[INFO] 节点 {chunk.chunk_id} 提炼成功，生成了 {len(knowledge.qa_pairs)} 个QA对")
            else:
                print(f"[WARNING] 节点 {chunk.chunk_id} 提炼结果类型不正确，使用空知识占位")
                knowledge = DistilledKnowledge(
                    summary="", qa_pairs=[], hypothetical_questions=[], entities={}
                )
        except Exception as e:
            print(f"[ERROR] 知识提炼步骤出错 (chunk: {chunk.chunk_id}): {e}")
            knowledge = DistilledKnowledge(
                summary="", qa_pairs=[], hypothetical_questions=[], entities={}
            )

        # 创建并返回富集块
        return EnrichedChunk(**chunk.model_dump(), knowledge=knowledge)

    def _distill_hierarchically(self, chunks: List[Chunk]) -> List[EnrichedChunk]:
        """自顶向下地处理所有文本块，实现状态化树状遍历，支持并行处理。

        此方法构建一个明确的父子关系图，并使用深度优先搜索(DFS)策略，
        严格按照从根节点到叶子节点的顺序处理所有chunk。在处理过程中，
        维护一个状态缓存，用于存储已处理节点的提炼结果，特别是其summary。

        支持并行处理同级节点，大幅提升处理速度。

        Args:
            chunks: 待处理的文本块列表

        Returns:
            包含知识提炼结果的 EnrichedChunk 列表
        """
        # 1. 构建父子关系图
        children_map: DefaultDict[str, List[Chunk]] = defaultdict(list)
        id_to_chunk: Dict[str, Chunk] = {}
        roots: List[Chunk] = []

        # 将所有块按ID索引，并构建父子关系图
        for ch in chunks:
            id_to_chunk[ch.chunk_id] = ch
            parent_id = ch.metadata.get("parent_id")
            if parent_id:
                children_map[parent_id].append(ch)
            else:
                roots.append(ch)

        print(
            f"[DEBUG] 构建了层级树: {len(roots)} 个根节点, {len(children_map)} 个有子节点的节点")

        # 2. 初始化结果容器和状态缓存
        enriched: List[EnrichedChunk] = []
        # 状态缓存: chunk_id -> 该chunk的提炼结果(特别是summary)
        summary_cache: Dict[str, str] = {}

        # 用于线程安全操作的锁
        from threading import Lock
        cache_lock = Lock()
        results_lock = Lock()

        # 3. 定义处理单个节点的函数
        def _process_node(node: Chunk, parent_summary: str = "") -> EnrichedChunk:
            # 处理当前节点，使用父节点摘要作为上下文
            enriched_node = self._distill_chunk_with_context(
                node, parent_summary)

            # 线程安全地更新缓存和结果
            with cache_lock:
                summary_cache[node.chunk_id] = enriched_node.knowledge.summary

            with results_lock:
                enriched.append(enriched_node)

                # 计算并显示进度
                elapsed = time.time() - self.start_time
                progress = len(enriched) / len(chunks) * 100
                eta = elapsed / max(len(enriched), 1) * \
                    (len(chunks) - len(enriched))
                print(
                    f"[进度] {progress:.1f}% 完成 ({len(enriched)}/{len(chunks)}) | 已用时间: {elapsed:.1f}秒 | 预计剩余: {eta:.1f}秒")

            return enriched_node

        # 4. 定义层级处理函数，支持并行处理同级节点
        def _process_level(nodes: List[Chunk], level: int = 0) -> None:
            if not nodes:
                return

            print(f"[INFO] 处理第 {level} 层，共 {len(nodes)} 个节点")

            # 为每个节点准备父级摘要
            node_with_parent_summary: List[Tuple[Chunk, str]] = []
            for node in nodes:
                parent_id = node.metadata.get("parent_id")
                parent_summary = ""
                if parent_id and parent_id in summary_cache:
                    parent_summary = summary_cache[parent_id]
                elif parent_id:
                    print(
                        f"[WARNING] 节点 {node.chunk_id} 的父节点 {parent_id} 未找到摘要")
                node_with_parent_summary.append((node, parent_summary))

            # 并行处理当前层级的所有节点
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_node = {executor.submit(_process_node, node, parent_summary): node
                                  for node, parent_summary in node_with_parent_summary}

                # 等待所有任务完成
                for future in concurrent.futures.as_completed(future_to_node):
                    node = future_to_node[future]
                    try:
                        future.result()  # 获取结果，但我们已经在_process_node中处理了
                    except Exception as e:
                        print(f"[ERROR] 处理节点 {node.chunk_id} 时出错: {e}")

            # 收集所有子节点，准备处理下一层
            next_level_nodes: List[Chunk] = []
            for node in nodes:
                children = children_map.get(node.chunk_id, [])
                next_level_nodes.extend(children)

            # 递归处理下一层
            if next_level_nodes:
                _process_level(next_level_nodes, level + 1)

        # 5. 开始处理，从根节点开始
        self.start_time = time.time()
        print(f"[INFO] 开始并行层级化知识提炼，从 {len(roots)} 个根节点开始...")
        _process_level(roots)

        elapsed = time.time() - self.start_time
        print(f"[INFO] 层级化知识提炼完成，共处理 {len(enriched)} 个节点，耗时 {elapsed:.2f} 秒")
        return enriched

    def _synthesize_global_knowledge(
        self, enriched_chunks: List[EnrichedChunk], batch_size: int = 50
    ) -> List[AuthoritativeKnowledgeUnit]:
        """将多个富集文本块直接整合为权威知识单元列表。
        
        使用分批处理策略，避免单次处理过多数据导致性能问题。
        
        Args:
            enriched_chunks: 富集文本块列表
            batch_size: 每批处理的最大块数，默认50
            
        Returns:
            权威知识单元列表
        """
        if not enriched_chunks:
            return []
            
        # 如果数据量很小，直接处理
        if len(enriched_chunks) <= batch_size:
            return self._process_knowledge_batch(enriched_chunks)
        
        # 数据量大时，分批处理
        print(f"[INFO] 数据量较大，采用分批处理策略，每批最多 {batch_size} 个块")
        
        # 1. 先按实体类型分组，尽量保持相关内容在同一批次
        entity_groups = {}
        no_entity_chunks = []
        
        for chunk in enriched_chunks:
            entities = chunk.knowledge.entities or {}
            if not entities:
                no_entity_chunks.append(chunk)
                continue
                
            # 使用第一个实体类型作为分组依据
            entity_type = next(iter(entities.keys()), None)
            if entity_type:
                if entity_type not in entity_groups:
                    entity_groups[entity_type] = []
                entity_groups[entity_type].append(chunk)
            else:
                no_entity_chunks.append(chunk)
        
        # 2. 将分组后的数据再按批次大小划分
        batches = []
        
        # 处理有实体类型的组
        for entity_type, chunks in entity_groups.items():
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i+batch_size]
                batches.append(batch)
        
        # 处理无实体类型的块
        for i in range(0, len(no_entity_chunks), batch_size):
            batch = no_entity_chunks[i:i+batch_size]
            batches.append(batch)
        
        # 3. 并行处理所有批次
        print(f"[INFO] 共划分为 {len(batches)} 个批次进行处理")
        all_results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(self.max_workers, len(batches))) as executor:
            future_to_batch = {executor.submit(self._process_knowledge_batch, batch): i 
                              for i, batch in enumerate(batches)}
            
            for future in concurrent.futures.as_completed(future_to_batch):
                batch_index = future_to_batch[future]
                try:
                    batch_result = future.result()
                    all_results.extend(batch_result)
                    print(f"[INFO] 批次 {batch_index+1}/{len(batches)} 处理完成，生成 {len(batch_result)} 个知识单元")
                except Exception as e:
                    print(f"[ERROR] 批次 {batch_index+1}/{len(batches)} 处理失败: {e}")
        
        # 4. 合并结果，去重
        unique_categories = {}
        for unit in all_results:
            category = unit.category
            if category not in unique_categories:
                unique_categories[category] = unit
            else:
                # 合并相同类别的QA对
                existing = unique_categories[category]
                existing.qa_pairs.extend(unit.qa_pairs)
                # 合并来源块
                existing.source_chunks = list(set(existing.source_chunks + unit.source_chunks))
        
        return list(unique_categories.values())
    
    def _process_knowledge_batch(
        self, batch_chunks: List[EnrichedChunk]
    ) -> List[AuthoritativeKnowledgeUnit]:
        """处理单批次知识块。"""
        template = self.prompt_manager.get_prompt(
            "global_knowledge_synthesis_prompt"
        )
        base_parser = PydanticOutputParser(
            pydantic_object=AuthoritativeKnowledgeList
        )
        fixing_parser = OutputFixingParser.from_llm(
            llm=self.client, parser=base_parser
        )
        prompt_template = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=template.get("system", "")),
                HumanMessagePromptTemplate.from_template(
                    template.get("user", "") + "\n{format_instructions}"
                ),
            ]
        )
        chain = prompt_template | self.client | fixing_parser
        
        # 优化：只保留必要字段，减少JSON大小
        payload = [
            {
                "chunk_id": c.chunk_id,
                "summary": c.knowledge.summary,
                # 过滤空QA对
                "qa_pairs": [qa for qa in c.knowledge.qa_pairs if qa.get("question") and qa.get("answer")],
                "entities": c.knowledge.entities,
            }
            for c in batch_chunks
        ]
        
        # 过滤掉没有QA对的块，减少处理量
        filtered_payload = [p for p in payload if p["qa_pairs"]]
        
        if not filtered_payload:
            return []
            
        try:
            response = chain.invoke(
                {
                    "enriched_chunks": json.dumps(filtered_payload, ensure_ascii=False),
                    "format_instructions": base_parser.get_format_instructions(),
                }
            )
            if isinstance(response, AuthoritativeKnowledgeList):
                return response.root
        except Exception as e:
            print(f"全局知识合成步骤出错: {e}")
        return []

    def build(
        self, 
        chunks: List[Chunk], 
        max_workers: int = None,
        skip_global_synthesis: bool = False,
        batch_size: int = 50
    ) -> List[AuthoritativeKnowledgeUnit] | List[Dict]:
        """对外提供的主入口。

        正确编排层级化知识提炼流程，包括：
        1. 调用重构后的 _distill_hierarchically 方法，执行完整的、状态化的层级提炼
        2. 将得到的 enriched_chunks 列表传给 _synthesize_global_knowledge 方法进行最终的全局整合

        Args:
            chunks: 待处理的文本块列表
            max_workers: 可选，并行处理的最大线程数，默认使用初始化时设置的值
            skip_global_synthesis: 可选，是否跳过第二阶段全局整合，直接返回QA对列表
            batch_size: 可选，第二阶段分批处理的批次大小

        Returns:
            如果 skip_global_synthesis=False，返回权威知识单元列表
            如果 skip_global_synthesis=True，返回QA对字典列表，每个字典包含问题、答案和来源块ID
        """
        # 更新并行处理线程数（如果提供）
        if max_workers is not None:
            self.max_workers = max_workers

        total_start_time = time.time()
        print(
            f"[INFO] 开始层级化知识构建流程，共有 {len(chunks)} 个文本块待处理，并行线程数: {self.max_workers}")

        # 第一阶段：执行状态化的层级提炼
        phase1_start = time.time()
        print("[INFO] 第一阶段: 执行状态化的层级提炼...")
        enriched_chunks = self._distill_hierarchically(chunks)
        phase1_time = time.time() - phase1_start
        print(
            f"[INFO] 层级提炼完成，共生成 {len(enriched_chunks)} 个富集块，耗时 {phase1_time:.2f} 秒")
        
        # 如果选择跳过第二阶段，直接返回扁平化的QA对列表
        if skip_global_synthesis:
            print("[INFO] 跳过第二阶段，直接返回原始QA对...")
            flat_qa_pairs = []
            for chunk in enriched_chunks:
                for qa_pair in chunk.knowledge.qa_pairs:
                    if qa_pair.get("question") and qa_pair.get("answer"):
                        flat_qa_pairs.append({
                            "question": qa_pair["question"],
                            "answer": qa_pair["answer"],
                            "source_chunk": chunk.chunk_id,
                            "header_chain": " > ".join(chunk.metadata.get("header_chain", [])),
                        })
            print(f"[INFO] 共生成 {len(flat_qa_pairs)} 个QA对")
            return flat_qa_pairs

        # 第二阶段：全局知识整合
        phase2_start = time.time()
        print("[INFO] 第二阶段: 执行全局知识整合...")
        authoritative_units = self._synthesize_global_knowledge(
            enriched_chunks, batch_size=batch_size)
        phase2_time = time.time() - phase2_start
        print(
            f"[INFO] 全局知识整合完成，共生成 {len(authoritative_units)} 个权威知识单元，耗时 {phase2_time:.2f} 秒")

        total_time = time.time() - total_start_time
        print(f"[INFO] 整个知识构建流程完成，总耗时 {total_time:.2f} 秒")

        return authoritative_units


__all__ = ["HierarchicalKnowledgeBuilder"]
