"""Demo script for Revision Prompt 9 — the morning decision workflow,
driven end-to-end by a controllable clock over a synthetic market day.

Nothing here reads the real wall clock to make a scheduling decision:
every `decide_schedule()` call below is handed an explicit `now_utc`
that this script advances by hand, exactly the property that makes the
schedule "reproducible" and "testable" (docs/MORNING_PLAN_SPEC.md) —
the required tests in `tests/test_morning_plan_scheduler.py` exercise
the same mechanism in isolation; this script narrates it end-to-end
against the real API and the real dev database, including a simulated
worker crash and restart mid-FINAL-run.

Run with: `python -m tradingos_api.scripts.demo_prompt9`
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from tradingos_api.db.session import SessionLocal
from tradingos_api.main import app
from tradingos_api.models.enums import MorningPlanRunStatus
from tradingos_api.models.morning_plan import MorningPlanRun
from tradingos_api.services.market_calendar import resolve_trading_day
from tradingos_api.services.morning_plan_scheduler import (
    STUCK_RUN_TIMEOUT,
    ScheduleDecision,
    decide_schedule,
)

client = TestClient(app)

# 2026-08-17 is a Monday — a real trading day, not a holiday, no early
# close. PDT (America/Los_Angeles daylight time in August) is UTC-7.
_PLAN_DATE = "2026-08-17"


def _pt(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 17, hour + 7, minute, tzinfo=UTC)


def _print_decision(label: str, decision: ScheduleDecision) -> None:
    print(f"  [{label}] should_run={decision.should_run} reason={decision.reason!r}")


def _print_section_counts(version: dict[str, Any]) -> None:
    for section in version["sections"]:
        print(f"    {section['section_key']}: {len(section['items'])} item(s)")


def main() -> None:
    print("=== 0. THE CALENDAR ITSELF: WEEKEND AND HOLIDAY ARE SKIPPED WITH A REASON ===")
    weekend = resolve_trading_day(datetime(2026, 8, 15).date())  # a Saturday
    holiday = resolve_trading_day(datetime(2026, 9, 7).date())  # Labor Day
    print(
        f"  2026-08-15 (Saturday): is_trading_day={weekend.is_trading_day} — {weekend.skip_reason}"
    )
    print(
        f"  2026-09-07 (Labor Day): is_trading_day={holiday.is_trading_day} — {holiday.skip_reason}"
    )

    scheduler_db = SessionLocal()
    try:
        print(f"\n=== 1. BEFORE THE PRELIMINARY WINDOW (05:00 PT, {_PLAN_DATE}) ===")
        too_early = decide_schedule(scheduler_db, now_utc=_pt(5, 0))
        _print_decision("05:00 PT", too_early)
        assert too_early.should_run is False

        print(f"\n=== 2. PRELIMINARY WINDOW OPENS (05:45 PT, {_PLAN_DATE}) ===")
        preliminary_decision = decide_schedule(scheduler_db, now_utc=_pt(5, 45))
        _print_decision("05:45 PT", preliminary_decision)
        assert preliminary_decision.should_run is True
        assert preliminary_decision.version_label is not None
        preliminary_response = client.post(
            "/api/v1/morning-plan/generate",
            json={
                "plan_date": _PLAN_DATE,
                "version_label": preliminary_decision.version_label.value,
                "triggered_by": "worker-demo",
                "idempotency_key": preliminary_decision.idempotency_key,
            },
        )
        assert preliminary_response.status_code == 201, preliminary_response.text
        preliminary_version = preliminary_response.json()
        print(
            f"  PRELIMINARY version #{preliminary_version['version_number']} "
            f"({preliminary_version['id']}), "
            f"completeness={preliminary_version['completeness_status']}"
        )
        _print_section_counts(preliminary_version)

        print("\n=== 3. A SECOND POLL TICK MINUTES LATER — DUPLICATE PROTECTION ===")
        duplicate_tick = decide_schedule(scheduler_db, now_utc=_pt(5, 50))
        _print_decision("05:50 PT", duplicate_tick)
        assert duplicate_tick.should_run is False

        print("\n=== 4. FINAL WINDOW OPENS (06:10 PT) — BUT THE WORKER CRASHES MID-RUN ===")
        final_decision_attempt_1 = decide_schedule(scheduler_db, now_utc=_pt(6, 10))
        _print_decision("06:10 PT, attempt 1", final_decision_attempt_1)
        assert final_decision_attempt_1.should_run is True
        assert final_decision_attempt_1.idempotency_key is not None
        # Simulate a worker process that started the run and then died
        # before recording any outcome — the row is left `RUNNING`
        # forever from the database's point of view.
        crashed_run = MorningPlanRun(
            plan_date=final_decision_attempt_1.plan_date,
            triggered_by="worker-demo",
            status=MorningPlanRunStatus.RUNNING,
            idempotency_key=final_decision_attempt_1.idempotency_key,
            started_at=_pt(6, 10),
        )
        scheduler_db.add(crashed_run)
        scheduler_db.commit()
        print(f"  (simulated crash: run {crashed_run.id} left RUNNING with no outcome recorded)")

        print("\n=== 5. A RESTARTED WORKER'S NEXT TICK, STILL WITHIN THE TIMEOUT ===")
        still_blocked = decide_schedule(scheduler_db, now_utc=_pt(6, 12))
        _print_decision("06:12 PT", still_blocked)
        assert still_blocked.should_run is False

        print(f"\n=== 6. PAST THE {STUCK_RUN_TIMEOUT} STUCK-RUN TIMEOUT ===")
        print("=== RETRY ATTEMPT 2 SUCCEEDS ===")
        retry_decision = decide_schedule(scheduler_db, now_utc=_pt(6, 26))
        _print_decision("06:26 PT, attempt 2", retry_decision)
        assert retry_decision.should_run is True
        assert retry_decision.attempt == 2
        assert retry_decision.version_label is not None
        final_response = client.post(
            "/api/v1/morning-plan/generate",
            json={
                "plan_date": _PLAN_DATE,
                "version_label": retry_decision.version_label.value,
                "triggered_by": "worker-demo",
                "idempotency_key": retry_decision.idempotency_key,
            },
        )
        assert final_response.status_code == 201, final_response.text
        final_version = final_response.json()
        print(
            f"  FINAL version #{final_version['version_number']} ({final_version['id']}), "
            f"completeness={final_version['completeness_status']}"
        )
        _print_section_counts(final_version)
        print(
            f"  delivery_events recorded: "
            f"{[e['channel'] for e in final_version['delivery_events']]}"
        )
    finally:
        scheduler_db.close()

    print("\n=== 7. THE DASHBOARD ONCE FINAL IS PUBLISHED ===")
    dashboard = client.get(
        "/api/v1/morning-plan/dashboard",
        params={"plan_date": _PLAN_DATE, "now": final_version["generated_at"]},
    )
    assert dashboard.status_code == 200
    top_status = dashboard.json()["top_status"]
    print(
        f"  plan_status={top_status['plan_status']} label={top_status['plan_version_label']} "
        f"regime={top_status['regime_classification']} "
        f"total_equity={top_status['total_equity']} exposure_pct={top_status['exposure_pct']}"
    )

    print("\n=== 8. PRELIMINARY-TO-FINAL DIFF ===")
    history = client.get(
        "/api/v1/morning-plan/versions", params={"plan_date": _PLAN_DATE, "limit": 200}
    )
    for row in history.json()["items"]:
        print(f"  version #{row['version_number']}: {row['version_label']}")
    preliminary_counts = {
        s["section_key"]: len(s["items"]) for s in preliminary_version["sections"]
    }
    final_counts = {s["section_key"]: len(s["items"]) for s in final_version["sections"]}
    for key in sorted(set(preliminary_counts) | set(final_counts)):
        before, after = preliminary_counts.get(key, 0), final_counts.get(key, 0)
        if before != after:
            print(f"  CHANGED {key}: {before} -> {after}")
    if preliminary_counts == final_counts:
        print("  (no section-count changes between PRELIMINARY and FINAL this run)")

    print("\n=== 9. MARKDOWN EXPORT ===")
    export = client.get(f"/api/v1/morning-plan/versions/{final_version['id']}/export.md")
    assert export.status_code == 200
    preview = "\n".join(export.text.splitlines()[:8])
    print(preview)
    print("  ...")

    print("\n=== 10. COWORK READ-ONLY BRIEF ===")
    tomorrow_no_plan = client.get(
        "/api/v1/morning-plan/cowork-brief", params={"plan_date": "2026-08-18"}
    )
    print(f"  a date with no FINAL plan yet -> {tomorrow_no_plan.status_code}")
    assert tomorrow_no_plan.status_code == 404
    brief = client.get("/api/v1/morning-plan/cowork-brief", params={"plan_date": _PLAN_DATE})
    assert brief.status_code == 200
    print(f"  {_PLAN_DATE} -> {brief.status_code}, version_label={brief.json()['version_label']}")

    print(
        "\nPrompt 9 demo complete — PRELIMINARY and FINAL versions persisted to the dev database."
    )


if __name__ == "__main__":
    main()
