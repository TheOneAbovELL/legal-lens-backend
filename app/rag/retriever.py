from qdrant_client import QdrantClient
import os

COLLECTION_NAME = "legal-lens-qdrant"
VECTOR_SIZE = 1024

client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY")
)

def retrieve_documents(query_embedding, limit=5):
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=limit
    )

    documents = []

    for point in results.points:
        payload = point.payload
        documents.append({
            "id": point.id,
            "score": point.score,
            "payload": payload
        })

    return documents
