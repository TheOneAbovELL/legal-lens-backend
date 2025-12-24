from fastapi import APIRouter
from app.schemas.search import SearchRequest
from app.services.rag_service import RAGService

router = APIRouter(prefix="/search", tags=["Search"])

rag = RAGService()

@router.post("/")
def search(request: SearchRequest):
    chunk = rag.retrieve(request.query)

    return {
        "content": chunk["content"],
        "source": chunk["source"]
    }
