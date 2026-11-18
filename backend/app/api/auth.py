from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import RateLimiter, check_password, create_token, current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
login_limiter = RateLimiter(per_minute=10)        # slows down password guessing against the dashboard


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=80)
    password: str = Field(..., max_length=200)


@router.post("/login")
def login(body: LoginRequest):
    if not login_limiter.allow(body.username):
        raise HTTPException(429, "Too many login attempts, try again in a minute")
    if not check_password(body.username, body.password):
        raise HTTPException(401, "Invalid username or password")
    return {"access_token": create_token(body.username), "token_type": "bearer", "user": body.username}


@router.get("/me")
def me(user: str = Depends(current_user)):
    return {"user": user}
