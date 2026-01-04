from fastapi import APIRouter
from app.schemas.chat import ChatRequest
from app.services.llm import ask_llm
from app.services.rag_service import RAGService

router = APIRouter(prefix="/chat", tags=["Chat"])

rag = RAGService()

@router.post("/")
def chat(request: ChatRequest):
    # STEP 1: Try retrieving context from Qdrant
    chunk = rag.retrieve_from_qdrant(request.query)

    # STEP 2: If Qdrant fails or returns nothing, fallback to local file
    if chunk is None:
        chunk = rag.retrieve(request.query)
        source = "local"
    else:
        source = "qdrant"

    # STEP 3: Build grounded prompt
    prompt = f"""
You are a legal assistant.
Answer the question strictly using the legal context below.

Legal Context:
{chunk['content']}

Question:
{request.query}
"""

    # STEP 4: Ask LLM
    answer = ask_llm(prompt)

    # STEP 5: Return response (schema unchanged)
    return {
        "answer": answer,
        "source": source
    }
