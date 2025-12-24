from app.services.document_loader import load_legal_documents
from app.services.text_splitter import chunk_documents
from app.services.embeddings import embed_texts
from app.services.semantic_search import find_most_relevant_chunk

class RAGService:
    def __init__(self):
        documents = load_legal_documents()
        self.chunks = chunk_documents(documents)
        texts = [chunk["content"] for chunk in self.chunks]
        self.vectors = embed_texts(texts)

        # simple in-memory cache
        self.cache = {}

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
