"""Morning plan endpoint tests (Revision Prompt R3). The one explicitly
required behavior: reruns create new versions, they never overwrite an
existing one."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


class TestRerunCreatesVersionsNotOverwrites:
    def test_two_reruns_produce_two_versions_with_increasing_numbers(
        self, client: TestClient, db_session: Session
    ) -> None:
        plan_date = "2026-08-06"
        first = client.post(
            "/api/v1/morning-plan/rerun",
            json={"plan_date": plan_date, "version_label": "AD_HOC", "triggered_by": "test"},
        )
        assert first.status_code == 201, first.text
        second = client.post(
            "/api/v1/morning-plan/rerun",
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
        first = client.post("/api/v1/morning-plan/rerun", json=payload)
        second = client.post("/api/v1/morning-plan/rerun", json=payload)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]

    def test_latest_reflects_most_recent_version_across_dates(self, client: TestClient) -> None:
        client.post(
            "/api/v1/morning-plan/rerun",
            json={"plan_date": "2026-08-08", "triggered_by": "test"},
        )
        latest = client.get("/api/v1/morning-plan/latest")
        assert latest.status_code == 200
        assert latest.json()["plan_date"] == "2026-08-08"
