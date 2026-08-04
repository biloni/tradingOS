"""OpenAPI contract tests (docs/TASKS.md Phase 8 requirement).

Two things are checked, deliberately not "diff the entire OpenAPI JSON
byte-for-byte" — that snapshot is enormous, churns on every docstring
edit, and would make every future PR touch an unreadable fixture:

1. A **path/method snapshot** (`fixtures/openapi_paths_snapshot.json`):
   every route across all 12 API areas is accounted for, and any
   accidental route removal/addition fails loudly with a readable diff.
2. **Structural invariants** that encode this project's actual API
   contract rules (ADR-031: money/quantity fields serialize as JSON
   strings, never numbers — a real bug class if it regressed silently).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from tradingos_api.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"

client = TestClient(app)


def _load_openapi() -> dict[str, Any]:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return cast(dict[str, Any], response.json())


def test_path_method_snapshot_matches() -> None:
    spec = _load_openapi()
    actual = sorted((path, sorted(methods.keys())) for path, methods in spec["paths"].items())
    expected = json.loads((FIXTURES_DIR / "openapi_paths_snapshot.json").read_text())
    expected = [(path, methods) for path, methods in expected]
    assert actual == expected, (
        "OpenAPI path/method set changed. If this is an intentional route "
        "addition/removal, update tests/fixtures/openapi_paths_snapshot.json."
    )


def test_all_12_api_areas_are_present() -> None:
    spec = _load_openapi()
    prefixes = {
        "/api/v1/instruments",
        "/api/v1/watchlists",
        "/api/v1/market",
        "/api/v1/recommendations",
        "/api/v1/portfolio",
        "/api/v1/orders",
        "/api/v1/journal",
        "/api/v1/performance",
        "/api/v1/alerts",
        "/api/v1/plans",
        "/api/v1/backtests",
        "/api/v1/settings",
    }
    paths = list(spec["paths"].keys())
    for prefix in prefixes:
        assert any(p.startswith(prefix) for p in paths), f"no route found under {prefix}"


class TestDecimalFieldsSerializeAsStrings:
    """ADR-031: every Numeric-backed field is a JSON string on the wire,
    never a float — this is what lets the frontend treat decimal-as-string
    as a first-class contract instead of silently losing precision."""

    def _schema_property(
        self, spec: dict[str, Any], schema_name: str, field: str
    ) -> dict[str, Any]:
        schemas = spec["components"]["schemas"]
        assert schema_name in schemas, f"{schema_name} missing from OpenAPI schemas"
        props = schemas[schema_name]["properties"]
        assert field in props, f"{field} missing from {schema_name}"
        return cast(dict[str, Any], props[field])

    def test_order_quantity_and_limit_price_are_strings(self) -> None:
        spec = _load_openapi()
        for field in ("quantity", "limit_price"):
            prop = self._schema_property(spec, "OrderResponse", field)
            # nullable fields are wrapped in anyOf: [{type: string, ...}, {type: null}]
            candidates = prop.get("anyOf", [prop])
            assert any(c.get("type") == "string" for c in candidates), (
                f"OrderResponse.{field} must serialize as a string, got {prop}"
            )

    def test_cash_summary_fields_are_strings(self) -> None:
        spec = _load_openapi()
        for field in ("cash", "starting_cash"):
            prop = self._schema_property(spec, "CashSummaryResponse", field)
            assert prop.get("type") == "string", (
                f"CashSummaryResponse.{field} must serialize as a string, got {prop}"
            )

    def test_risk_policy_percentages_are_strings(self) -> None:
        spec = _load_openapi()
        prop = self._schema_property(spec, "RiskPolicyResponse", "max_position_pct")
        assert prop.get("type") == "string"
