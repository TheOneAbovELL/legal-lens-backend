from dotenv import load_dotenv
load_dotenv()   #THIS LINE LOADS .env

from fastapi import FastAPI
from app.api.v1.auth import router as auth_router
from app.api.v1.search import router as search_router
from app.api.v1.chat import router as chat_router

from fastapi.middleware.cors import CORSMiddleware
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


app.include_router(auth_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")

@app.get("/")
def root():
    return {"status": "ok"}
