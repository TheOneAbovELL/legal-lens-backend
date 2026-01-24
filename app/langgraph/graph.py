from typing import TypedDict, Optional, List, Dict
import re
from langgraph.graph import StateGraph

IPC_TO_BNS = {
    "420": "318",   # Cheating
    "302": "103",   # Murder
}

class GraphState(TypedDict):
    query: str
    intent: Optional[str]
    safe: Optional[bool]
    keyword_results: Optional[List[Dict]]
    vector_results: Optional[List[Dict]]
    retrieved_docs: Optional[List[Dict]]
    ipc_bns_map: Optional[Dict[str, str]]
    response: Optional[str]


def intent_detect(state: GraphState) -> GraphState:
    query = state["query"].lower()

    if any(word in query for word in ["ipc", "section", "bns", "act"]):
        state["intent"] = "legal_query"
    else:
        state["intent"] = "general_query"

    return state

def safety_guard(state: GraphState) -> GraphState:
    unsafe_terms = ["forge", "fake", "threaten", "blackmail"]

    query = state["query"].lower()
    state["safe"] = not any(term in query for term in unsafe_terms)

    return state

def keyword_search(query: str) -> List[Dict]:
    corpus = [
        {
            "text": "Section 420 IPC deals with cheating.",
            "source": "Doc-1"
        },
        {
            "text": "Section 302 IPC relates to punishment for murder.",
            "source": "Doc-2"
        }
    ]

    return [
        doc for doc in corpus
        if any(word in doc["text"].lower() for word in query.lower().split())
    ]

def vector_search(query: str) -> List[Dict]:
    # Simulated semantic match
    return [
        {
            "text": "Cheating under IPC includes dishonest inducement.",
            "source": "Vec-1",
            "score": 0.85
        }
    ]

def retrieve(state: GraphState) -> GraphState:
    if not state.get("safe"):
        state["retrieved_docs"] = []
        return state

    query = state["query"]

    keyword_results = keyword_search(query)
    vector_results = vector_search(query)

    state["keyword_results"] = keyword_results
    state["vector_results"] = vector_results

    # Simple reranking: keyword first, then vector
    combined = keyword_results + vector_results

    state["retrieved_docs"] = combined[:3]

    return state

def bns_mapper(state: GraphState) -> GraphState:
    text = state["query"] + " "

    for doc in state.get("retrieved_docs", []):
        text += doc.get("text", "") + " "

    ipc_sections = re.findall(r"(?:section\s*)?(\d{3})\s*ipc", text.lower())

    mapping = {}
    for ipc in ipc_sections:
        if ipc in IPC_TO_BNS:
            mapping[f"IPC {ipc}"] = f"BNS {IPC_TO_BNS[ipc]}"

    state["ipc_bns_map"] = mapping
    return state

def generate(state: GraphState) -> GraphState:
    if not state.get("retrieved_docs"):
        state["response"] = "The query could not be processed safely."
        return state

    # Base response from retrieved context
    context = state["retrieved_docs"][0]["text"]
    response = f"Based on the legal context: {context}"

    # Add IPC → BNS mapping if available
    if state.get("ipc_bns_map"):
        response += "\n\nIPC → BNS Mapping:\n"
        for ipc, bns in state["ipc_bns_map"].items():
            response += f"- {ipc} → {bns}\n"

    state["response"] = response
    return state


from langgraph.graph import StateGraph

graph = StateGraph(GraphState)

graph.add_node("IntentDetect", intent_detect)
graph.add_node("SafetyGuard", safety_guard)
graph.add_node("Retrieve", retrieve)
graph.add_node("BNSMapper", bns_mapper)
graph.add_node("Generate", generate)

graph.set_entry_point("IntentDetect")

graph.add_edge("IntentDetect", "SafetyGuard")
graph.add_edge("SafetyGuard", "Retrieve")
graph.add_edge("Retrieve", "BNSMapper")
graph.add_edge("BNSMapper", "Generate")


app_graph = graph.compile()

if __name__ == "__main__":
    result = app_graph.invoke(
        {"query": "Explain Section 420 IPC"}
    )
    print("\nFINAL STATE OUTPUT:\n")
    print(result)



