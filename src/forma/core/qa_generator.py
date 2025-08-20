"""Utilities for generating FAQ-style question and answers."""

from __future__ import annotations

from typing import Any, Dict, List
import json

from langchain.text_splitter import MarkdownTextSplitter
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config import get_vlm_config
from .prompt_manager import PromptManager


class QAGenerator:
    """Encapsulates the multi-stage QA generation workflow."""

    def __init__(
        self,
        prompt_manager: PromptManager | None = None,
        client: ChatOpenAI | None = None,
    ) -> None:
        cfg = get_vlm_config()
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

        splitter = MarkdownTextSplitter()
        chunks = splitter.split_text(md_content)
        template = self.prompt_manager.get_prompt("qa_generation")
        results: List[Dict[str, str]] = []
        for chunk in chunks:
            prompt = {
                "system": template.get("system"),
                "user": template.get("user", "").replace("{context}", chunk),
            }
            response = self._invoke(prompt)
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                continue
            if isinstance(data, list):
                for item in data:
                    if (
                        isinstance(item, dict)
                        and item.get("question")
                        and item.get("answer")
                    ):
                        results.append(
                            {
                                "question": item["question"],
                                "answer": item["answer"],
                            }
                        )
        return results

    def run_categorization_stage(self, questions: List[str]) -> List[str]:
        """Derive a global list of categories from questions."""

        template = self.prompt_manager.get_prompt("category_generation")
        question_list = "\n".join(questions)
        prompt = {
            "system": template.get("system"),
            "user": template.get("user", "").replace("{question_list}", question_list),
        }
        response = self._invoke(prompt)
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            return []
        categories = data.get("categories")
        if isinstance(categories, list):
            return [str(c) for c in categories if c]
        return []

    def run_synthesis_stage(
        self, raw_qas: List[Dict[str, str]], categories: List[str]
    ) -> List[Dict[str, str]]:
        """Cluster, synthesise and categorise QA pairs."""

        if not raw_qas:
            return []
        questions = [qa["question"] for qa in raw_qas]
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import KMeans

        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(questions)
        n_clusters = min(len(raw_qas), max(1, len(categories) or 1))
        kmeans = KMeans(n_clusters=n_clusters, n_init=10, random_state=0)
        labels = kmeans.fit_predict(embeddings)
        clusters: Dict[int, List[Dict[str, str]]] = {}
        for label, qa in zip(labels, raw_qas):
            clusters.setdefault(int(label), []).append(qa)

        template = self.prompt_manager.get_prompt("qa_synthesis")
        category_list = json.dumps(categories, ensure_ascii=False)
        results: List[Dict[str, str]] = []
        for group in clusters.values():
            qa_cluster = json.dumps(group, ensure_ascii=False)
            prompt = {
                "system": template.get("system"),
                "user": template.get("user", "")
                .replace("{category_list}", category_list)
                .replace("{qa_cluster}", qa_cluster),
            }
            response = self._invoke(prompt)
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(data, dict)
                and data.get("question")
                and data.get("answer")
                and data.get("category")
            ):
                results.append(
                    {
                        "question": data["question"],
                        "answer": data["answer"],
                        "category": data["category"],
                    }
                )
        return results


__all__ = ["QAGenerator"]
