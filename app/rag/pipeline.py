from app.embeddings.embedder import embed_query
from app.rag.retriever import retrieve_documents

def rag_retrieve(query: str):
    embedding = embed_query(query)
    documents = retrieve_documents(embedding)
    return documents
