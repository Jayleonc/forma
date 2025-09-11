"""Knowledge building workflow utilities for hierarchical processing."""

from __future__ import annotations

from typing import Any, Dict, List, DefaultDict
from collections import defaultdict
import json

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
    ) -> None:
        cfg = get_llm_config()
        print(cfg)
        self.client = client or ChatOpenAI(
            model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url
        )
        self.prompt_manager = prompt_manager or PromptManager()

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
        """在层级上下文中处理单个文本块。"""
        template = self.prompt_manager.get_prompt(
            "hierarchical_knowledge_distillation_prompt"
        )
        base_parser = PydanticOutputParser(pydantic_object=DistilledKnowledge)
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

        header_chain = " > ".join(chunk.metadata.get("header_chain", []))
        try:
            response = chain.invoke(
                {
                    "chunk_text": chunk.text,
                    "header_chain": header_chain,
                    "parent_summary": parent_summary,
                    "format_instructions": base_parser.get_format_instructions(),
                }
            )
            knowledge = (
                response
                if isinstance(response, DistilledKnowledge)
                else DistilledKnowledge(
                    summary="", qa_pairs=[], hypothetical_questions=[], entities={}
                )
            )
        except Exception as e:
            print(f"知识提炼步骤出错 (chunk: {chunk.chunk_id}): {e}")
            knowledge = DistilledKnowledge(
                summary="", qa_pairs=[], hypothetical_questions=[], entities={}
            )
        return EnrichedChunk(**chunk.model_dump(), knowledge=knowledge)

    def _distill_hierarchically(self, chunks: List[Chunk]) -> List[EnrichedChunk]:
        """自顶向下地处理所有文本块。"""
        children_map: DefaultDict[str, List[Chunk]] = defaultdict(list)
        roots: List[Chunk] = []
        for ch in chunks:
            parent_id = ch.metadata.get("parent_id")
            if parent_id:
                children_map[parent_id].append(ch)
            else:
                roots.append(ch)

        enriched: List[EnrichedChunk] = []

        def _dfs(node: Chunk, parent_summary: str) -> None:
            enriched_node = self._distill_chunk_with_context(node, parent_summary)
            enriched.append(enriched_node)
            summary = enriched_node.knowledge.summary
            for child in children_map.get(node.chunk_id, []):
                _dfs(child, summary)

        for root in roots:
            _dfs(root, "")

        return enriched

    def _synthesize_global_knowledge(
        self, enriched_chunks: List[EnrichedChunk]
    ) -> List[AuthoritativeKnowledgeUnit]:
        """将多个富集文本块直接整合为权威知识单元列表。"""
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
        payload = [
            {
                "chunk_id": c.chunk_id,
                "summary": c.knowledge.summary,
                "qa_pairs": c.knowledge.qa_pairs,
                "hypothetical_questions": c.knowledge.hypothetical_questions,
                "entities": c.knowledge.entities,
            }
            for c in enriched_chunks
        ]
        try:
            response = chain.invoke(
                {
                    "enriched_chunks": json.dumps(payload, ensure_ascii=False),
                    "format_instructions": base_parser.get_format_instructions(),
                }
            )
            if isinstance(response, AuthoritativeKnowledgeList):
                return response.root
        except Exception as e:
            print(f"全局知识合成步骤出错: {e}")
        return []

    def build(self, chunks: List[Chunk]) -> List[AuthoritativeKnowledgeUnit]:
        """对外提供的主入口。"""
        enriched_chunks = self._distill_hierarchically(chunks)
        return self._synthesize_global_knowledge(enriched_chunks)


__all__ = ["HierarchicalKnowledgeBuilder"]
