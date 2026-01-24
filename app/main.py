from dotenv import load_dotenv
load_dotenv()   # THIS LINE LOADS .env

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.api.v1.auth import router as auth_router
from app.api.v1.search import router as search_router
from app.api.v1.chat import router as chat_router

from app.langgraph.graph import app_graph, stream_response


app = FastAPI(title="Legal Lens")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://172.25.210.149:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Existing routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")

# Health check
@app.get("/")
def root():
    return {"status": "ok"}

# ✅ NEW: Streaming query endpoint (Phase 5)
@app.post("/api/v1/query/stream")
def stream_query(payload: dict):
    query = payload.get("query", "")

    # Run LangGraph pipeline
    state = app_graph.invoke({"query": query})

    # Stream response with citation markers
    return StreamingResponse(
        stream_response(state),
        media_type="text/plain"
    )
