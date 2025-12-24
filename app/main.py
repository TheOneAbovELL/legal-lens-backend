from dotenv import load_dotenv
load_dotenv()   #THIS LINE LOADS .env

from fastapi import FastAPI
from app.api.v1.auth import router as auth_router
from app.api.v1.search import router as search_router
from app.api.v1.chat import router as chat_router

app = FastAPI(title="Legal Lens")

app.include_router(auth_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")

@app.get("/")
def root():
    return {"status": "ok"}
