"""Shared request/response building blocks used across every Phase 8
router — one pagination envelope and one error-response shape, so a
client only has to learn each pattern once (docs/API_CONTRACTS.md).

**Error responses**: this API uses FastAPI's standard `HTTPException`,
which serializes as `{"detail": "<message>"}` — the same shape every
shipped-MVP endpoint already used (docs/API_CONTRACTS.md, unchanged).
`ErrorResponse` below exists only to give that shape a name in the
OpenAPI schema for documentation purposes.

**Authorization**: every router assumes a single authenticated user
(ADR-007 — no auth in this system). `owner_user_id` filtering is applied
using `get_current_user_id()` (core/dependencies.py), which resolves to
the one seeded `UserProfile` row — the seam a real multi-user auth layer
would replace later without changing any router's business logic.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    detail: str


class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
