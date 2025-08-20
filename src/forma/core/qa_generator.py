"""Utilities for generating FAQ-style question and answers."""

from __future__ import annotations

from typing import Any, Dict, List
import json

import numpy as np
from langchain.text_splitter import MarkdownTextSplitter
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config import get_vlm_config
from .prompt_manager import PromptManager
from ..utils.device import DEVICE


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

        # --- 向量化 --- #
        # 1. 加载一个高效的句子嵌入模型。
        # sentence-transformers 框架极大地简化了文本向量化的过程。
        # 'all-MiniLM-L6-v2' 是一个轻量且性能优秀的多语言模型。
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2", device=DEVICE)

        # 2. 将所有原始问题的文本转换为向量（Embeddings）。
        # 这些向量是问题在多维空间中的数学表示，语义相近的问题，其向量也相近。
        questions = [qa["question"] for qa in raw_qas]
        embeddings = model.encode(questions)

        # --- 语义聚类 --- #
        # 3. 使用DBSCAN算法进行语义聚类。
        # DBSCAN的优势在于无需预先指定聚类的数量，它可以根据数据本身的分布自动发现簇。
        # 它还能识别出无法归入任何簇的“噪音点”，帮助我们过滤低质量或孤立的问题。
        # eps: 定义了邻域的半径，metric='cosine'表示使用余弦距离。
        # min_samples: 定义了形成一个核心点所需的最小样本数。
        from sklearn.cluster import DBSCAN
        dbscan = DBSCAN(eps=0.4, min_samples=1, metric='cosine')
        labels = dbscan.fit_predict(embeddings)

        # 4. 将问答对按照聚类结果进行分组。
        # 标签为 -1 的是噪音点，我们将其忽略。
        clusters: Dict[int, List[Dict[str, str]]] = {}
        for label, qa in zip(labels, raw_qas):
            if label != -1:
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
