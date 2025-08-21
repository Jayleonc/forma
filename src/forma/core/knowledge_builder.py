"""Knowledge building workflow utilities."""

from __future__ import annotations

from typing import Any, Dict, List
import json

from langchain.output_parsers import PydanticOutputParser, OutputFixingParser
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config import get_llm_config
from .prompt_manager import PromptManager
from .models import (
    Chunk,
    DistilledKnowledge,
    EnrichedChunk,
    AuthoritativeKnowledgeUnit,
)


class KnowledgeBuilder:
    """Encapsulates the multi-stage knowledge building workflow."""

    def __init__(
        self,
        prompt_manager: PromptManager | None = None,
        client: ChatOpenAI | None = None,
    ) -> None:
        cfg = get_llm_config()
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
        """Distil knowledge from a single chunk."""
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
            print(f"Knowledge distillation error for chunk {chunk.chunk_id}: {e}")
            knowledge = DistilledKnowledge(
                summary="", qa_pairs=[], hypothetical_questions=[], entities={}
            )
        return EnrichedChunk(**chunk.model_dump(), knowledge=knowledge)

    def _discover_global_themes(self, enriched_chunks: List[EnrichedChunk]) -> List[Dict]:
        """Discover global themes across enriched chunks."""
        template = self.prompt_manager.get_prompt("theme_generation_prompt")
        prompt_template = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=template.get("system", "")),
                HumanMessagePromptTemplate.from_template(template.get("user", "")),
            ]
        )
        payload = [
            {
                "chunk_id": c.chunk_id,
                "summary": c.knowledge.summary,
                "questions": [qa["question"] for qa in c.knowledge.qa_pairs]
                + c.knowledge.hypothetical_questions,
            }
            for c in enriched_chunks
        ]
        chain = prompt_template | self.client
        try:
            result = chain.invoke({"enriched_chunks": json.dumps(payload, ensure_ascii=False)})
            text = getattr(result, "content", "") if hasattr(result, "content") else result
            return json.loads(text) if text else []
        except Exception as e:
            print(f"Theme discovery error: {e}")
            return []

    def _fuse_knowledge_by_theme(
        self, theme: str, related_chunks: List[EnrichedChunk]
    ) -> AuthoritativeKnowledgeUnit:
        """Fuse knowledge for a specific theme into an authoritative unit."""
        template = self.prompt_manager.get_prompt("theme_synthesis_prompt")
        base_parser = PydanticOutputParser(pydantic_object=AuthoritativeKnowledgeUnit)
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
        payload = [
            {
                "chunk_id": c.chunk_id,
                "summary": c.knowledge.summary,
                "qa_pairs": c.knowledge.qa_pairs,
                "hypothetical_questions": c.knowledge.hypothetical_questions,
                "entities": c.knowledge.entities,
            }
            for c in related_chunks
        ]
        try:
            response = chain.invoke(
                {
                    "theme": theme,
                    "related_knowledge": json.dumps(payload, ensure_ascii=False),
                    "format_instructions": base_parser.get_format_instructions(),
                }
            )
            if isinstance(response, AuthoritativeKnowledgeUnit):
                return response
        except Exception as e:
            print(f"Theme synthesis error for theme {theme}: {e}")
        return AuthoritativeKnowledgeUnit(
            theme=theme,
            canonical_question="",
            canonical_answer="",
            source_chunks=[c.chunk_id for c in related_chunks],
        )


__all__ = ["KnowledgeBuilder"]
