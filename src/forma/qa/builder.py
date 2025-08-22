"""Knowledge building workflow utilities."""

from __future__ import annotations

from typing import Any, Dict, List
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


class KnowledgeBuilder:
    """封装多阶段的知识构建工作流。"""

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

    def _distill_knowledge_from_chunk(self, chunk: Chunk) -> EnrichedChunk:
        """从单个文本块中提炼知识。"""
        template = self.prompt_manager.get_prompt(
            "knowledge_distillation_prompt")
        base_parser = PydanticOutputParser(pydantic_object=DistilledKnowledge)
        fixing_parser = OutputFixingParser.from_llm(
            llm=self.client, parser=base_parser)

        prompt_template = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=template.get("system", "")),
                HumanMessagePromptTemplate.from_template(
                    template.get("user", "") + "\n{format_instructions}"
                ),
            ]
        )

        chain = prompt_template | self.client | fixing_parser

        try:
            response = chain.invoke(
                {
                    "chunk_text": chunk.text,
                    "format_instructions": base_parser.get_format_instructions(),
                }
            )
            knowledge = response if isinstance(response, DistilledKnowledge) else DistilledKnowledge(
                summary="", qa_pairs=[], hypothetical_questions=[], entities={}
            )
        except Exception as e:
            print(f"知识提炼步骤出错 (chunk: {chunk.chunk_id}): {e}")
            knowledge = DistilledKnowledge(
                summary="", qa_pairs=[], hypothetical_questions=[], entities={}
            )
        return EnrichedChunk(**chunk.model_dump(), knowledge=knowledge)

    def distill_knowledge_in_batch(self, chunks: List[Chunk]) -> List[EnrichedChunk]:
        """批量处理多个文本块的知识提炼任务，使用 LangChain 的 `chain.batch()` 并发调用。

        Args:
            chunks: 待处理的文本块列表。

        Returns:
            包含知识提炼结果的 `EnrichedChunk` 列表，顺序与输入保持一致。
        """
        template = self.prompt_manager.get_prompt("knowledge_distillation_prompt")
        base_parser = PydanticOutputParser(pydantic_object=DistilledKnowledge)
        fixing_parser = OutputFixingParser.from_llm(llm=self.client, parser=base_parser)

        prompt_template = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=template.get("system", "")),
                HumanMessagePromptTemplate.from_template(
                    template.get("user", "") + "\n{format_instructions}"
                ),
            ]
        )
        chain = prompt_template | self.client | fixing_parser

        # 构造批量输入
        batch_inputs = [
            {
                "chunk_text": ch.text,
                "format_instructions": base_parser.get_format_instructions(),
            }
            for ch in chunks
        ]

        # 执行批量调用
        try:
            batch_results = chain.batch(batch_inputs)
        except Exception as e:
            print(f"知识批量提炼步骤出错: {e}")
            batch_results = [None] * len(chunks)

        # 解析结果，保证健壮性
        enriched_chunks: List[EnrichedChunk] = []
        for ch, res in zip(chunks, batch_results):
            if isinstance(res, DistilledKnowledge):
                knowledge = res
            else:
                print(f"chunk {ch.chunk_id} 提炼失败，将使用空知识占位。")
                knowledge = DistilledKnowledge(
                    summary="",
                    qa_pairs=[],
                    hypothetical_questions=[],
                    entities={},
                )
            enriched_chunks.append(EnrichedChunk(**ch.model_dump(), knowledge=knowledge))
        return enriched_chunks

    # 第三阶段：全局知识整合
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


__all__ = ["KnowledgeBuilder"]
