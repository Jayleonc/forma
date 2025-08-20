from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field, RootModel


class RawQA(BaseModel):
    """Single QA pair."""

    question: str = Field(..., description="Question extracted from the document")
    answer: str = Field(..., description="Answer extracted from the document, must originate from the source text")


RawQAList = RootModel[List[RawQA]]


class CategoryList(BaseModel):
    """Pydantic model for list of categories."""

    categories: List[str]


class SynthQA(BaseModel):
    """Synthesised QA with assigned category."""

    question: str
    answer: str
    category: str
