"""Auth request/response schemas."""

import uuid

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    """User registration."""

    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    """User login."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Token refresh."""

    refresh_token: str


class UserResponse(BaseModel):
    """Public user info."""

    id: uuid.UUID
    username: str
    email: str
    preferred_language: str

    model_config = {"from_attributes": True}
