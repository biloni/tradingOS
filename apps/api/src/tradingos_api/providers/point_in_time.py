"""Shared point-in-time contract every Revision Prompt 4 provider
interface's response DTOs compose (docs/DATA_DICTIONARY.md's point-in-time
requirements): `published_at`/`observed_at`/`source`/`provider_record_id`/
`revision_id` are the fields every evidence type must carry regardless of
which of the 15 interfaces produced it. `usable_at` is deliberately NOT
part of this shared envelope — it is a judgment the *ingestion service*
makes (accounting for a given evidence type's own propagation delay), not
something a provider adapter can know on its own, so it is computed at
write time in `services/ingest_evidence.py`, never fabricated here.

Capability metadata and failure exceptions are NOT shared across
interfaces (each interface file below defines its own) — only this
common evidence envelope is, since it is the one part of the point-in-time
requirement that is genuinely identical for every interface.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PointInTimeEnvelope(BaseModel):
    """Compose this into every provider response DTO (see
    `providers/*.py` below) rather than repeating these five fields."""

    published_at: datetime | None
    observed_at: datetime
    source: str
    provider_record_id: str | None = None
    revision_id: str | None = None


class ProviderCapabilities(BaseModel):
    """Base every interface-specific `XCapabilities` model subclasses.
    `is_live_data=False` marks a synthetic/fixture-backed implementation
    honestly — never disguised as a real vendor call."""

    provider_name: str
    is_live_data: bool
