from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.dependencies.auth import get_current_user
from app.models import User
from app.schemas.auth import SignupRequest, LoginRequest, TokenResponse, UserResponse

router=APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/signup", response_model=TokenResponse, status_code=201, summary="Register a user")
def signup(payload: SignupRequest, db: Session=Depends(get_db)):
    if db.scalar(select(User).where(User.email==payload.email.lower())):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user=User(full_name=payload.full_name.strip(), email=payload.email.lower(), password_hash=hash_password(payload.password), role=payload.role)
    db.add(user); db.commit(); db.refresh(user)
    return TokenResponse(
    access_token=create_access_token({
        "user_id": user.id,
        "email": user.email,
        "role": user.role.value,
    }),
    user=user,
)

@router.post("/login", response_model=TokenResponse, summary="Log in")
def login(payload: LoginRequest, db: Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==payload.email.lower()))
    if not user or not verify_password(payload.password,user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(
    access_token=create_access_token({
        "user_id": user.id,
        "email": user.email,
        "role": user.role.value,
    }),
    user=user,
)

@router.get("/me", response_model=UserResponse, summary="Get current user")
def me(user: User=Depends(get_current_user)): return user
