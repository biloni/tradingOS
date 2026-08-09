"""Morning plan endpoint tests (Revision Prompt R3 + Revision Prompt 9).
The one explicitly required R3 behavior: reruns create new versions,
they never overwrite an existing one — still true now that `/generate`
(Revision Prompt 9's real 12-stage orchestrator) is what actually
produces those versions, replacing R3's original empty-version stub."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


class TestRerunCreatesVersionsNotOverwrites:
    def test_two_reruns_produce_two_versions_with_increasing_numbers(
        self, client: TestClient, db_session: Session
    ) -> None:
        plan_date = "2026-08-06"  # a Thursday — a real trading day
        first = client.post(
            "/api/v1/morning-plan/generate",
            json={"plan_date": plan_date, "version_label": "AD_HOC", "triggered_by": "test"},
        )
        assert first.status_code == 201, first.text
        second = client.post(
            "/api/v1/morning-plan/generate",
            json={"plan_date": plan_date, "version_label": "CORRECTION", "triggered_by": "test"},
        )
        assert second.status_code == 201, second.text

        first_body = first.json()
        second_body = second.json()
        assert first_body["id"] != second_body["id"]
        assert second_body["version_number"] == first_body["version_number"] + 1

        # Both rows still exist in the DB — the first was never deleted
        # or mutated by the second rerun.
        still_present = db_session.execute(
            text("SELECT count(*) FROM morning_plan_versions WHERE id = ANY(:ids)"),
            {"ids": [first_body["id"], second_body["id"]]},
        ).scalar()
        assert still_present == 2

        history = client.get(
            "/api/v1/morning-plan/versions", params={"plan_date": plan_date, "limit": 200}
        )
        assert history.status_code == 200
        version_numbers = {row["version_number"] for row in history.json()["items"]}
        assert {first_body["version_number"], second_body["version_number"]} <= version_numbers

    def test_rerun_with_same_idempotency_key_returns_same_version(self, client: TestClient) -> None:
        key = f"test-rerun-{uuid.uuid4()}"
        payload = {"plan_date": "2026-08-07", "triggered_by": "test", "idempotency_key": key}
        first = client.post("/api/v1/morning-plan/generate", json=payload)
        second = client.post("/api/v1/morning-plan/generate", json=payload)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]

    def test_latest_reflects_most_recent_version_across_dates(self, client: TestClient) -> None:
        # A date safely after `demo_prompt9.py`'s hardcoded 2026-08-17 —
        # that script commits real, non-rolled-back rows straight to the
        # dev database via its own `TestClient(app)` calls (unlike this
        # fixture's `client`, whose `db_session` rolls back), so `/latest`
        # (global across every plan_date) would otherwise see whichever
        # of the two is chronologically later, not whichever this test
        # just posted.
        client.post(
            "/api/v1/morning-plan/generate",
            json={"plan_date": "2026-08-20", "triggered_by": "test"},  # a Thursday
        )
        latest = client.get("/api/v1/morning-plan/latest")
        assert latest.status_code == 200
        assert latest.json()["plan_date"] == "2026-08-20"

    def test_generate_on_a_non_trading_day_is_rejected_with_the_reason(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/morning-plan/generate",
            json={"plan_date": "2026-08-08", "triggered_by": "test"},  # a Saturday
        )
        assert response.status_code == 422
        assert "weekend" in response.json()["detail"].lower()


class TestPreliminaryToFinalDiff:
    """The required "plan preliminary-to-final diff" category — a
    PRELIMINARY run in the morning followed by a FINAL run later the
    same trading day must both persist as distinct, independently
    retrievable versions (never one overwriting the other), with the
    dashboard and `/latest` always preferring the more authoritative
    FINAL once it exists."""

    def test_preliminary_then_final_are_both_retained_and_final_outranks_it(
        self, client: TestClient
    ) -> None:
        # Also after `demo_prompt9.py`'s hardcoded 2026-08-17 — see the
        # comment on `test_latest_reflects_most_recent_version_across_dates`
        # above; this test's own `/latest` assertion has the same
        # dependency on being chronologically the newest plan_date.
        plan_date = "2026-08-19"  # a Wednesday — a real trading day
        preliminary = client.post(
            "/api/v1/morning-plan/generate",
            json={"plan_date": plan_date, "version_label": "PRELIMINARY", "triggered_by": "test"},
        )
        assert preliminary.status_code == 201, preliminary.text
        final = client.post(
            "/api/v1/morning-plan/generate",
            json={"plan_date": plan_date, "version_label": "FINAL", "triggered_by": "test"},
        )
        assert final.status_code == 201, final.text

        preliminary_body = preliminary.json()
        final_body = final.json()
        assert preliminary_body["id"] != final_body["id"]
        assert preliminary_body["version_label"] == "PRELIMINARY"
        assert final_body["version_label"] == "FINAL"
        assert final_body["version_number"] > preliminary_body["version_number"]

        history = client.get(
            "/api/v1/morning-plan/versions", params={"plan_date": plan_date, "limit": 200}
        )
        labels = {row["id"]: row["version_label"] for row in history.json()["items"]}
        assert labels[preliminary_body["id"]] == "PRELIMINARY"
        assert labels[final_body["id"]] == "FINAL"

        dashboard = client.get(
            "/api/v1/morning-plan/dashboard",
            params={"plan_date": plan_date, "now": final_body["generated_at"]},
        )
        assert dashboard.status_code == 200
        dashboard_body = dashboard.json()
        # FINAL outranks PRELIMINARY even though both exist — the
        # dashboard never shows an interim draft once the day's official
        # plan has been published.
        assert dashboard_body["top_status"]["plan_version_label"] == "FINAL"
        assert dashboard_body["version"]["id"] == final_body["id"]

        latest = client.get("/api/v1/morning-plan/latest")
        assert latest.json()["id"] == final_body["id"]

    def test_cowork_brief_only_ever_serves_the_final_version(self, client: TestClient) -> None:
        plan_date = "2026-08-13"  # a Thursday
        before_final = client.get(
            "/api/v1/morning-plan/cowork-brief", params={"plan_date": plan_date}
        )
        assert before_final.status_code == 404

        preliminary = client.post(
            "/api/v1/morning-plan/generate",
            json={"plan_date": plan_date, "version_label": "PRELIMINARY", "triggered_by": "test"},
        )
        assert preliminary.status_code == 201

        # Still no FINAL yet — a PRELIMINARY draft must never substitute.
        still_before_final = client.get(
            "/api/v1/morning-plan/cowork-brief", params={"plan_date": plan_date}
        )
        assert still_before_final.status_code == 404

        final = client.post(
            "/api/v1/morning-plan/generate",
            json={"plan_date": plan_date, "version_label": "FINAL", "triggered_by": "test"},
        )
        assert final.status_code == 201

        brief = client.get("/api/v1/morning-plan/cowork-brief", params={"plan_date": plan_date})
        assert brief.status_code == 200
        assert brief.json()["id"] == final.json()["id"]
        assert brief.json()["version_label"] == "FINAL"

    def test_export_markdown_renders_the_requested_version(self, client: TestClient) -> None:
        plan_date = "2026-08-14"  # a Friday
        generated = client.post(
            "/api/v1/morning-plan/generate",
            json={"plan_date": plan_date, "triggered_by": "test"},
        )
        assert generated.status_code == 201
        version_id = generated.json()["id"]

        export = client.get(f"/api/v1/morning-plan/versions/{version_id}/export.md")
        assert export.status_code == 200
        assert export.headers["content-type"].startswith("text/markdown")
        assert f"Morning Decision Plan — {plan_date}" in export.text
