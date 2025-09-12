import sys
from typing import List, Dict, Any

import pytest

from src.forma.qa.builder_v2 import HierarchicalKnowledgeBuilder
from src.forma.shared.models import (
    Chunk,
    DistilledKnowledge,
    EnrichedChunk,
    AuthoritativeKnowledgeUnit,
)


class TestableHierarchicalBuilder(HierarchicalKnowledgeBuilder):
    """A test subclass that avoids actual LLM calls and records traversal.

    - Overrides `_distill_chunk_with_context` to return deterministic knowledge and
      record the received `parent_summary` for assertions.
    - Overrides `_synthesize_global_knowledge` to build a simple unit from
      collected enriched chunks without LLM.
    """

    def __init__(self):
        super().__init__(prompt_manager=None, client=None)
        self.calls: List[Dict[str, Any]] = []

    def _distill_chunk_with_context(self, chunk: Chunk, parent_summary: str) -> EnrichedChunk:  # type: ignore[override]
        # Record the call for order and context verification
        self.calls.append({
            "chunk_id": chunk.chunk_id,
            "parent_summary": parent_summary,
            "header_chain": list(chunk.metadata.get("header_chain", [])),
        })
        # Create a deterministic summary for this chunk
        summary = f"SUM({chunk.chunk_id})"
        knowledge = DistilledKnowledge(
            summary=summary,
            qa_pairs=[{
                "question": f"Q about {chunk.chunk_id}",
                "answer": f"A uses parent: {parent_summary or 'NONE'}",
            }],
            hypothetical_questions=[f"HQ for {chunk.chunk_id}"],
            entities={"chunk_ids": [chunk.chunk_id]},
        )
        return EnrichedChunk(**chunk.model_dump(), knowledge=knowledge)

    def _synthesize_global_knowledge(self, enriched_chunks: List[EnrichedChunk]) -> List[AuthoritativeKnowledgeUnit]:  # type: ignore[override]
        # Aggregate all qa_pairs into one unit to simulate FAQ generation
        qa_pairs = []
        for c in enriched_chunks:
            qa_pairs.extend(c.knowledge.qa_pairs)
        # Print for visibility during test run
        print("[TEST-OUTPUT] Synthesized QA Pairs:")
        for qa in qa_pairs:
            print(f"- {qa['question']} => {qa['answer']}")
        return [AuthoritativeKnowledgeUnit(category="test", qa_pairs=qa_pairs, source_chunks=[c.chunk_id for c in enriched_chunks])]


def make_chunk(chunk_id: str, text: str, parent_id: str | None, header_chain: list[str]):
    return Chunk(chunk_id=chunk_id, text=text, metadata={
        "parent_id": parent_id,
        "source_filename": "unit_test.md",
        "header_chain": header_chain,
        "sibling_ids": [],
    })


def test_hierarchical_distillation_parent_before_child_and_backfill():
    # Build a simple hierarchy: root -> child
    root = make_chunk("root", "## Root Section\nRoot content.", None, ["Root"])
    child = make_chunk("child", "### Child Section\nChild content.", "root", ["Root", "Child"])

    # An additional sibling under root to exercise ordering among multiple children
    child2 = make_chunk("child2", "### Child2 Section\nChild2 content.", "root", ["Root", "Child2"])

    chunks = [child, root, child2]  # Intentionally unordered input

    builder = TestableHierarchicalBuilder()

    # Run only the hierarchical distillation to validate ordering and context
    enriched = builder._distill_hierarchically(chunks)

    # Assert that calls are ordered: root first, then its children (in DFS order)
    call_order = [c["chunk_id"] for c in builder.calls]
    assert call_order[0] == "root", f"Expected root first, got {call_order}"
    assert set(call_order[1:]) == {"child", "child2"}, f"Expected children next, got {call_order}"

    # Find recorded parent_summary used for child and child2
    calls_by_id = {c["chunk_id"]: c for c in builder.calls}
    parent_summary_for_child = calls_by_id["child"]["parent_summary"]
    parent_summary_for_child2 = calls_by_id["child2"]["parent_summary"]

    # The parent's summary should be the deterministic summary from root
    assert parent_summary_for_child == "SUM(root)", f"Child should receive parent's summary, got: {parent_summary_for_child}"
    assert parent_summary_for_child2 == "SUM(root)", f"Child2 should receive parent's summary, got: {parent_summary_for_child2}"

    # Now synthesize to emulate FAQ generation and ensure some visible output
    units = builder._synthesize_global_knowledge(enriched)
    assert len(units) == 1
    assert len(units[0].qa_pairs) == 3  # root, child, child2

    # Additionally ensure the child's QA answer mentions parent summary
    child_qa = [qa for qa in units[0].qa_pairs if qa["question"] == "Q about child"][0]
    assert "SUM(root)" in child_qa["answer"], "Child QA should include backfilled parent summary"

    # Ensure the root used default NONE for parent_summary in its QA
    root_qa = [qa for qa in units[0].qa_pairs if qa["question"] == "Q about root"][0]
    assert "NONE" in root_qa["answer"], "Root should have no parent context"
