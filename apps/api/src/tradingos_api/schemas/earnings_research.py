"""Request/response shapes for `POST /api/v1/earnings-research` — an
on-demand, live-web-search research agent for any current S&P 500, Dow
Jones Industrial Average, or Nasdaq-100 constituent (services/earnings_research.py).
Deliberately not restricted to this app's own tracked-instrument universe
(`Instrument`) — the whole point is coverage beyond whatever small set is
already seeded, verified live against the index membership rather than a
maintained static list that would go stale."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class EarningsResearchRequest(BaseModel):
    company: str = Field(min_length=1, max_length=200)


class ResearchSource(BaseModel):
    url: str
    title: str | None = None


class EarningsResearchResponse(BaseModel):
    answer: str
    sources: list[ResearchSource]
    model_call_record_ids: list[uuid.UUID]
    iterations: int
