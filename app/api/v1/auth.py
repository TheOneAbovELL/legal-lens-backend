from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(request: LoginRequest):
    # Temporary placeholder auth logic
    if request.username == "admin" and request.password == "admin":
        return {
            "message": "Login successful",
            "user": request.username
        }

    return {
        "message": "Invalid credentials"
    }
