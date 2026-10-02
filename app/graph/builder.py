"""The canonical Legal Lens pipeline graph (the only RAG pipeline in the application).

START → understand → safety ─┬─ refuse ─────────────────────────────────────────────────→ END
                             ├─ small_talk ─────────────────────────────────────────────→ END
                             └─ classify ─┬─ plan_simple ───┐
                                          ├─ plan_moderate ─┼→ retrieve → rerank → fuse →
                                          └─ plan_complex ──┘
        map_provisions → validate_evidence ─┬─ (search mode) ───────────────────────────→ END
                                            ├─ insufficient ────────────────────────────→ END
                                            └─ generate → validate_answer ─┬─ (retry) → generate
                                                                           └────────────→ END
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import PipelineNodes, PipelineServices
from app.graph.state import PipelineMode, PipelineState, Route


def _after_safety(state: PipelineState) -> str:
    if state.route == Route.REFUSE:
        return "refuse"
    if state.route == Route.SMALL_TALK:
        return "small_talk"
    return "classify"


def _after_classify(state: PipelineState) -> str:
    return {Route.COMPLEX: "plan_complex", Route.MODERATE: "plan_moderate"}.get(state.route, "plan_simple")  # type: ignore[arg-type]


def _after_evidence(state: PipelineState) -> str:
    if state.options.mode == PipelineMode.SEARCH:
        return "end"
    if state.evidence is None or not state.evidence.sufficient:
        return "insufficient"
    return "generate"


def _after_answer(state: PipelineState) -> str:
    return "generate" if state.answer is None and state.corrective_feedback else "end"


def build_graph(services: PipelineServices) -> Any:
    nodes = PipelineNodes(services)
    graph = StateGraph(PipelineState)
    for name in (
        "understand", "safety", "refuse", "small_talk", "classify", "plan_simple", "plan_moderate",
        "plan_complex", "retrieve", "rerank", "fuse", "map_provisions", "validate_evidence",
        "insufficient", "generate", "validate_answer",
    ):
        graph.add_node(name, getattr(nodes, name))

    graph.add_edge(START, "understand")
    graph.add_edge("understand", "safety")
    graph.add_conditional_edges("safety", _after_safety, ["refuse", "small_talk", "classify"])
    graph.add_edge("refuse", END)
    graph.add_edge("small_talk", END)
    graph.add_conditional_edges("classify", _after_classify, ["plan_simple", "plan_moderate", "plan_complex"])
    for plan in ("plan_simple", "plan_moderate", "plan_complex"):
        graph.add_edge(plan, "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "fuse")
    graph.add_edge("fuse", "map_provisions")
    graph.add_edge("map_provisions", "validate_evidence")
    graph.add_conditional_edges(
        "validate_evidence", _after_evidence, {"end": END, "insufficient": "insufficient", "generate": "generate"}
    )
    graph.add_edge("insufficient", END)
    graph.add_edge("generate", "validate_answer")
    graph.add_conditional_edges("validate_answer", _after_answer, {"generate": "generate", "end": END})
    return graph.compile()
