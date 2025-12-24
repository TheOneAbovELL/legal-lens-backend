from fastapi import APIRouter
from app.schemas.chat import ChatRequest
from app.services.llm import ask_llm
from app.services.rag_service import RAGService

router = APIRouter(prefix="/chat", tags=["Chat"])

rag = RAGService()

@router.post("/")
def chat(request: ChatRequest):
    chunk = rag.retrieve(request.query)

    prompt = f"""
You are a legal assistant.
Answer the question strictly using the legal context below.

Legal Context:
{chunk['content']}

Question:
{request.query}
"""

    answer = ask_llm(prompt)

    return {
        "answer": answer,
        "source": chunk["source"]
    }
