from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    password: str


class StepUpRequest(BaseModel):
    password: str


class SessionStatusResponse(BaseModel):
    authenticated: bool
    stepped_up: bool = False
    expires_at: str | None = None
