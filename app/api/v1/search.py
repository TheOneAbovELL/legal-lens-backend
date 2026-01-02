from fastapi import APIRouter
from app.rag.pipeline import rag_retrieve

router = APIRouter()

@router.post("/search")
def search(query: str):
    documents = rag_retrieve(query)

    return {
        "answer": "Generated later",
        "sources": documents
    }
