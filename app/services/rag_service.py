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

        # ---------- QDRANT SETUP (NEW) ----------
        self.qdrant = QdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY")
        )
        self.collection_name = "legal-lens-qdrant"

    # ---------- LOCAL SEMANTIC SEARCH (FALLBACK) ----------
    def retrieve(self, query: str):
        if query in self.cache:
            return self.cache[query]

        chunk = find_most_relevant_chunk(
            query,
            self.chunks,
            self.vectors
        )

        self.cache[query] = chunk
        return chunk

    # ---------- QDRANT RETRIEVAL (PRIMARY) ----------
    def retrieve_from_qdrant(self, query: str):
        try:
            # Convert query to embedding
            query_vector = embed_texts([query])[0]

            # Query Qdrant
            results = self.qdrant.query(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=3
            )

            if not results:
                return None

            # Extract text from payload
            texts = []
            for r in results:
                if r.payload and "text" in r.payload:
                    texts.append(r.payload["text"])

            if not texts:
                return None

            return {
                "content": "\n\n".join(texts),
                "source": "qdrant"
            }

        except Exception as e:
            print("Qdrant retrieval failed:", e)
            return None
