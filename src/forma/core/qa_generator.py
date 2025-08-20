"""Utilities for generating FAQ-style question and answers."""

from __future__ import annotations

from typing import Any, Dict, List
import json

import numpy as np
# LangChain output parsing
from langchain.output_parsers import PydanticOutputParser, OutputFixingParser
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sentence_transformers import SentenceTransformer
from sklearn.cluster import DBSCAN

from ..config import get_openai_llm_config
from .prompt_manager import PromptManager
from ..utils.device import DEVICE
from .schemas import RawQAList, CategoryList, SynthQA


class QAGenerator:
    """Encapsulates the multi-stage QA generation workflow."""

    def __init__(
            self,
            prompt_manager: PromptManager | None = None,
            client: ChatOpenAI | None = None,
    ) -> None:
        cfg = get_openai_llm_config()

        print('base_url', cfg.base_url, 'model', cfg.model)

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

    def run_generation_stage(self, md_content: str) -> List[Dict[str, str]]:
        """Generate raw QA pairs from markdown content."""
        template = self.prompt_manager.get_prompt("qa_generation")
        base_parser = PydanticOutputParser(pydantic_object=RawQAList)
        fixing_parser = OutputFixingParser.from_llm(
            llm=self.client, parser=base_parser)

        prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=template.get("system", "")),
            HumanMessagePromptTemplate.from_template(
                template.get("user", "") + "\n{format_instructions}"
            )
        ])

        chain = prompt_template | self.client | fixing_parser

        try:
            # For debugging: check what variables the prompt template expects
            # print("Prompt expects:", prompt_template.input_variables)

            response_obj = chain.invoke({
                "context": md_content,
                "format_instructions": base_parser.get_format_instructions()
            })
            if response_obj and isinstance(response_obj, RawQAList):
                return [qa.model_dump() for qa in response_obj.root]
            return []
        except Exception as e:
            print(f"Generation parse error: {e}")
            return []

    def run_categorization_stage(self, questions: List[str]) -> List[str]:
        """Derive a global list of categories from questions."""
        template = self.prompt_manager.get_prompt("category_generation")
        base_parser = PydanticOutputParser(pydantic_object=CategoryList)
        fixing_parser = OutputFixingParser.from_llm(llm=self.client, parser=base_parser)

        prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=template.get("system", "")),
            HumanMessagePromptTemplate.from_template(
                template.get("user", "") + "\n{format_instructions}"
            )
        ])

        chain = prompt_template | self.client | fixing_parser

        try:
            question_list_str = "\n".join(questions)
            response_obj = chain.invoke({
                "question_list": question_list_str,
                "format_instructions": base_parser.get_format_instructions()
            })
            if response_obj and isinstance(response_obj, CategoryList):
                return response_obj.categories
            return []
        except Exception as e:
            print(f"Category parse error: {e}")
            return []

    def run_synthesis_stage(
            self, raw_qas: List[Dict[str, str]], categories: List[str]
    ) -> List[Dict[str, str]]:
        """Cluster, synthesise and categorise QA pairs."""
        if not raw_qas:
            return []

        template = self.prompt_manager.get_prompt("qa_synthesis")
        base_parser = PydanticOutputParser(pydantic_object=SynthQA)
        fixing_parser = OutputFixingParser.from_llm(llm=self.client, parser=base_parser)

        prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=template.get("system", "")),
            HumanMessagePromptTemplate.from_template(
                template.get("user", "") + "\n{format_instructions}"
            )
        ])

        chain = prompt_template | self.client | fixing_parser

        question_embeddings = self._get_embeddings([qa["question"] for qa in raw_qas])
        clusters = self._cluster_embeddings(question_embeddings)

        synthesised_qas = []
        category_list_str = "\n".join(categories)

        for i, cluster_indices in enumerate(clusters):
            if not cluster_indices:
                continue
            cluster_qa_pairs = [raw_qas[j] for j in cluster_indices]
            qa_cluster_str = json.dumps(cluster_qa_pairs, ensure_ascii=False, indent=2)

            try:
                response_obj = chain.invoke({
                    "qa_cluster": qa_cluster_str,
                    "category_list": category_list_str,
                    "format_instructions": base_parser.get_format_instructions(),
                })
                if response_obj and isinstance(response_obj, SynthQA) and response_obj.question and response_obj.answer:
                    synthesised_qas.append(response_obj.model_dump())
            except Exception as e:
                print(f"Synthesis parse error for cluster {i}: {e}")

        return synthesised_qas

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        model = SentenceTransformer("shibing624/text2vec-base-chinese", device=DEVICE)
        return model.encode(texts)

    def _cluster_embeddings(self, embeddings: np.ndarray) -> List[List[int]]:
        dbscan = DBSCAN(eps=0.5, min_samples=2, metric="cosine")
        cluster_labels = dbscan.fit_predict(embeddings)

        # Group indices by cluster label
        num_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
        clusters = [[] for _ in range(num_clusters)]
        for i, label in enumerate(cluster_labels):
            if label != -1:
                clusters[label].append(i)

        return clusters


__all__ = ["QAGenerator"]
