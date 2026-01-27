from app.services.graph_service import GraphService

from app.services.document_loader import load_legal_documents
from app.services.text_splitter import chunk_documents
from app.services.embeddings import embed_texts
from app.services.semantic_search import find_most_relevant_chunk

from qdrant_client import QdrantClient
import os


class RAGService:
    def __init__(self):
        # ---------- LOCAL RAG SETUP (UNCHANGED) ----------
        documents = load_legal_documents()
        self.chunks = chunk_documents(documents)

        texts = [chunk["content"] for chunk in self.chunks]
        self.vectors = embed_texts(texts)

        # simple in-memory cache
        self.cache = {}

        # ---------- QDRANT SETUP (UNCHANGED) ----------
        self.qdrant = QdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY")
        )
        self.collection_name = "legal-lens-qdrant"

        # ---------- NEO4J SETUP (ADDED, SAFE) ----------
        self.graph_service = GraphService()

    # ---------- LOCAL SEMANTIC SEARCH (FALLBACK) ----------
    def retrieve(self, query: str):
        if query in self.cache:
            return self.cache[query]

        chunk = find_most_relevant_chunk(
            query,
            self.chunks,
            self.vectors
        )

        # ---------- NEO4J CONTEXT (OPTIONAL, SAFE ADDITION) ----------
        try:
            graph_context = self.graph_service.get_statute_context(query)
            if graph_context:
                chunk["content"] += "\n\nRelated Legal Statutes:\n"
                chunk["content"] += "\n".join(graph_context)
        except Exception as e:
            # Neo4j failure must NOT affect RAG
            print("Neo4j retrieval failed:", e)

        self.cache[query] = chunk
        return chunk

    # ---------- QDRANT RETRIEVAL (PRIMARY, UNCHANGED) ----------
    def retrieve_from_qdrant(self, query: str):
        try:
            query_vector = embed_texts([query])[0]

            results = self.qdrant.query_points(
                collection_name=self.collection_name,
                prefetch=[],
                query=query_vector,
                limit=3
            )

            if not results or not results.points:
                return None

            texts = []
            for p in results.points:
                if p.payload and "text" in p.payload:
                    texts.append(p.payload["text"])

            if not texts:
                return None

            return {
                "content": "\n\n".join(texts),
                "source": "qdrant"
            }

        except Exception as e:
            print("Qdrant retrieval failed:", e)
            return None
