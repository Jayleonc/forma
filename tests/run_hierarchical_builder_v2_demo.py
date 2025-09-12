import os
import sys
import types
import importlib.util
from typing import List, Dict, Any

# Resolve paths
ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(ROOT, ".."))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
MODELS_PATH = os.path.join(SRC_ROOT, "forma", "shared", "models.py")
BUILDER_V2_PATH = os.path.join(SRC_ROOT, "forma", "qa", "builder_v2.py")

if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

# --- Create lightweight stubs to avoid external deps during demo ---
# Package scaffolding: forma, forma.shared
if 'forma' not in sys.modules:
    forma_pkg = types.ModuleType('forma')
    forma_pkg.__path__ = [os.path.join(SRC_ROOT, 'forma')]
    sys.modules['forma'] = forma_pkg
if 'forma.shared' not in sys.modules:
    shared_pkg = types.ModuleType('forma.shared')
    shared_pkg.__path__ = [os.path.join(SRC_ROOT, 'forma', 'shared')]
    sys.modules['forma.shared'] = shared_pkg

# Load real models into forma.shared.models (small, no heavy deps)
spec_models = importlib.util.spec_from_file_location('forma.shared.models', MODELS_PATH)
models_mod = importlib.util.module_from_spec(spec_models)  # type: ignore
assert spec_models and spec_models.loader, 'Failed to load models.py'
spec_models.loader.exec_module(models_mod)  # type: ignore
sys.modules['forma.shared.models'] = models_mod
from forma.shared.models import (  # type: ignore
    Chunk,
    DistilledKnowledge,
    EnrichedChunk,
    AuthoritativeKnowledgeUnit,
)

# Mock forma.shared.config
config_mod = types.ModuleType('forma.shared.config')
class _Cfg:
    model = 'dummy'
    api_key = 'dummy'
    base_url = 'http://dummy'
def get_llm_config():
    return _Cfg()
config_mod.get_llm_config = get_llm_config  # type: ignore
sys.modules['forma.shared.config'] = config_mod

# Mock forma.shared.prompts
prompts_mod = types.ModuleType('forma.shared.prompts')
class PromptManager:  # minimal stub
    def get_prompt(self, name: str):
        return {"system": "", "user": ""}
prompts_mod.PromptManager = PromptManager  # type: ignore
sys.modules['forma.shared.prompts'] = prompts_mod

# Mock langchain related modules to avoid heavy deps
lc_output_parsers = types.ModuleType('langchain.output_parsers')
class PydanticOutputParser:
    def __init__(self, pydantic_object):
        self._obj = pydantic_object
    def get_format_instructions(self):
        return "{}"
class OutputFixingParser:
    @classmethod
    def from_llm(cls, llm, parser):
        return parser
lc_output_parsers.PydanticOutputParser = PydanticOutputParser  # type: ignore
lc_output_parsers.OutputFixingParser = OutputFixingParser  # type: ignore
sys.modules['langchain.output_parsers'] = lc_output_parsers

lc_prompts = types.ModuleType('langchain.prompts')
class ChatPromptTemplate:
    @classmethod
    def from_messages(cls, msgs):
        return cls()
    def __or__(self, other):
        return self
class HumanMessagePromptTemplate:
    @classmethod
    def from_template(cls, t):
        return cls()
lc_prompts.ChatPromptTemplate = ChatPromptTemplate  # type: ignore
lc_prompts.HumanMessagePromptTemplate = HumanMessagePromptTemplate  # type: ignore
sys.modules['langchain.prompts'] = lc_prompts

lc_msgs = types.ModuleType('langchain_core.messages')
class HumanMessage:
    def __init__(self, content: str):
        self.content = content
class SystemMessage:
    def __init__(self, content: str):
        self.content = content
lc_msgs.HumanMessage = HumanMessage  # type: ignore
lc_msgs.SystemMessage = SystemMessage  # type: ignore
sys.modules['langchain_core.messages'] = lc_msgs

lc_openai = types.ModuleType('langchain_openai')
class ChatOpenAI:
    def __init__(self, model: str, api_key: str, base_url: str):
        pass
    def invoke(self, messages):
        class _R:
            content = ""
        return _R()
lc_openai.ChatOpenAI = ChatOpenAI  # type: ignore
sys.modules['langchain_openai'] = lc_openai

# Dynamically load builder_v2 with package name so relative imports resolve
spec = importlib.util.spec_from_file_location('forma.qa.builder_v2', BUILDER_V2_PATH)
builder_v2 = importlib.util.module_from_spec(spec)  # type: ignore
assert spec and spec.loader, 'Failed to load spec for builder_v2'
spec.loader.exec_module(builder_v2)  # type: ignore
HierarchicalKnowledgeBuilder = builder_v2.HierarchicalKnowledgeBuilder


class DemoHierarchicalBuilder(HierarchicalKnowledgeBuilder):
    """A demo subclass that avoids actual LLM calls and prints traversal.

    Overrides `_distill_chunk_with_context` and `_synthesize_global_knowledge`
    so we can run without network/LLM, but still observe behavior.
    """

    def __init__(self):
        super().__init__(prompt_manager=None, client=None)
        self.calls: List[Dict[str, Any]] = []

    def _distill_chunk_with_context(self, chunk: Chunk, parent_summary: str) -> EnrichedChunk:  # type: ignore[override]
        self.calls.append({
            "chunk_id": chunk.chunk_id,
            "parent_summary": parent_summary,
            "header_chain": list(chunk.metadata.get("header_chain", [])),
        })
        # Deterministic summary for visibility
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
        qa_pairs: List[Dict[str, str]] = []
        for c in enriched_chunks:
            qa_pairs.extend(c.knowledge.qa_pairs)
        print("\n[DEMO] Synthesized QA Pairs:")
        for qa in qa_pairs:
            print(f"- {qa['question']} => {qa['answer']}")
        return [AuthoritativeKnowledgeUnit(category="demo", qa_pairs=qa_pairs, source_chunks=[c.chunk_id for c in enriched_chunks])]


def make_chunk(chunk_id: str, text: str, parent_id: str | None, header_chain: list[str]):
    return Chunk(chunk_id=chunk_id, text=text, metadata={
        "parent_id": parent_id,
        "source_filename": "demo.md",
        "header_chain": header_chain,
        "sibling_ids": [],
    })


def main():
    # Build a small hierarchy: root -> (child, child2)
    root = make_chunk("root", "## Root\nRoot content.", None, ["Root"])
    child = make_chunk("child", "### Child\nChild content.", "root", ["Root", "Child"])
    child2 = make_chunk("child2", "### Child2\nChild2 content.", "root", ["Root", "Child2"])

    # Intentionally shuffle input order to ensure traversal, not input order, decides processing
    chunks = [child, root, child2]

    builder = DemoHierarchicalBuilder()
    enriched = builder._distill_hierarchically(chunks)

    print("\n[DEMO] Traversal order and parent summaries:")
    for call in builder.calls:
        print(f"  - node={call['chunk_id']}, parent_summary={call['parent_summary']}, header_chain={' > '.join(call['header_chain'])}")

    units = builder._synthesize_global_knowledge(enriched)

    print("\n[DEMO] Validation checks:")
    order = [c["chunk_id"] for c in builder.calls]
    print(f"  - Order: {order}")
    assert order[0] == "root", f"Expected 'root' first, got {order}"
    assert set(order[1:]) == {"child", "child2"}, f"Expected children after root, got {order}"

    calls_by_id = {c["chunk_id"]: c for c in builder.calls}
    assert calls_by_id["child"]["parent_summary"].startswith("SUM(root)"), "Child should use parent's summary"
    assert calls_by_id["child2"]["parent_summary"].startswith("SUM(root)"), "Child2 should use parent's summary"

    # Root uses NONE as there is no parent
    root_parent = calls_by_id["root"]["parent_summary"]
    assert root_parent == "", "Root should have empty parent summary before default messaging"

    print("\n[DEMO] All checks passed.")


if __name__ == "__main__":
    main()
