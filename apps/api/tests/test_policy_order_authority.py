"""Policy checks for the v2 amendment's four-tier order-authority
taxonomy (PROJECT_INSTRUCTIONS.md -> ORDER AUTHORITY). Pure unit tests —
no DB, no HTTP, no live provider — matching this repo's existing
fixtures-only test policy (docs/TEST_STRATEGY.md)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tradingos_api.policy.order_authority import (
    MAX_LIVE_CONFIRMATION_AGE,
    AutoPolicyGrant,
    OrderAuthorityDenied,
    OrderAuthorityMode,
    OrderConfirmation,
    assert_order_authorized,
    bracket_leg_requires_its_own_confirmation,
)

NOW = datetime(2026, 8, 5, 13, 0, tzinfo=UTC)


def _fresh_confirmation(**overrides: object) -> OrderConfirmation:
    defaults: dict[str, object] = {
        "confirmed_at": NOW,
        "account_id": "acct-live-1",
        "environment": "production",
        "broker_endpoint": "https://api.alpaca.markets",
    }
    defaults.update(overrides)
    return OrderConfirmation(**defaults)  # type: ignore[arg-type]


class TestFourModesExactly:
    def test_exactly_four_modes_no_live_auto(self) -> None:
        assert {m.value for m in OrderAuthorityMode} == {
            "RESEARCH_ONLY",
            "PAPER_MANUAL_APPROVAL",
            "PAPER_AUTO_POLICY",
            "LIVE_CONFIRM_EACH_ORDER",
        }
        assert not any("AUTO" in m.value and "LIVE" in m.value for m in OrderAuthorityMode)


class TestResearchOnly:
    def test_cannot_create_any_order_even_with_confirmation(self) -> None:
        with pytest.raises(OrderAuthorityDenied, match="RESEARCH_ONLY"):
            assert_order_authorized(
                OrderAuthorityMode.RESEARCH_ONLY,
                is_live=False,
                confirmation=_fresh_confirmation(),
                now=NOW,
            )

    def test_cannot_create_a_live_order(self) -> None:
        with pytest.raises(OrderAuthorityDenied):
            assert_order_authorized(OrderAuthorityMode.RESEARCH_ONLY, is_live=True, now=NOW)


class TestPaperManualApproval:
    def test_denied_without_confirmation(self) -> None:
        with pytest.raises(OrderAuthorityDenied, match="explicit confirmation"):
            assert_order_authorized(
                OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
                is_live=False,
                confirmation=None,
                now=NOW,
            )

    def test_authorized_with_confirmation(self) -> None:
        assert_order_authorized(
            OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
            is_live=False,
            confirmation=_fresh_confirmation(),
            now=NOW,
        )

    def test_cannot_place_a_live_order(self) -> None:
        with pytest.raises(OrderAuthorityDenied):
            assert_order_authorized(
                OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
                is_live=True,
                confirmation=_fresh_confirmation(),
                now=NOW,
            )


class TestPaperAutoPolicy:
    def test_denied_without_a_grant(self) -> None:
        with pytest.raises(OrderAuthorityDenied, match="explicitly enabled"):
            assert_order_authorized(OrderAuthorityMode.PAPER_AUTO_POLICY, is_live=False, now=NOW)

    def test_denied_when_grant_disabled(self) -> None:
        with pytest.raises(OrderAuthorityDenied):
            assert_order_authorized(
                OrderAuthorityMode.PAPER_AUTO_POLICY,
                is_live=False,
                auto_policy=AutoPolicyGrant(policy_version="v1", enabled=False),
                now=NOW,
            )

    def test_denied_when_version_missing(self) -> None:
        with pytest.raises(OrderAuthorityDenied):
            assert_order_authorized(
                OrderAuthorityMode.PAPER_AUTO_POLICY,
                is_live=False,
                auto_policy=AutoPolicyGrant(policy_version="", enabled=True),
                now=NOW,
            )

    def test_authorized_with_enabled_versioned_grant(self) -> None:
        assert_order_authorized(
            OrderAuthorityMode.PAPER_AUTO_POLICY,
            is_live=False,
            auto_policy=AutoPolicyGrant(policy_version="paper-auto-v1", enabled=True),
            now=NOW,
        )

    def test_cannot_place_a_live_order_regardless_of_grant(self) -> None:
        with pytest.raises(OrderAuthorityDenied):
            assert_order_authorized(
                OrderAuthorityMode.PAPER_AUTO_POLICY,
                is_live=True,
                auto_policy=AutoPolicyGrant(policy_version="v1", enabled=True),
                now=NOW,
            )


class TestLiveConfirmEachOrder:
    def test_authorized_with_fresh_unambiguous_confirmation(self) -> None:
        assert_order_authorized(
            OrderAuthorityMode.LIVE_CONFIRM_EACH_ORDER,
            is_live=True,
            confirmation=_fresh_confirmation(confirmed_at=NOW - timedelta(seconds=5)),
            now=NOW,
        )

    def test_denied_without_confirmation(self) -> None:
        with pytest.raises(OrderAuthorityDenied, match="requires a confirmation"):
            assert_order_authorized(
                OrderAuthorityMode.LIVE_CONFIRM_EACH_ORDER,
                is_live=True,
                confirmation=None,
                now=NOW,
            )

    def test_denied_when_confirmation_is_stale(self) -> None:
        stale_at = NOW - MAX_LIVE_CONFIRMATION_AGE - timedelta(seconds=1)
        with pytest.raises(OrderAuthorityDenied, match="not fresh"):
            assert_order_authorized(
                OrderAuthorityMode.LIVE_CONFIRM_EACH_ORDER,
                is_live=True,
                confirmation=_fresh_confirmation(confirmed_at=stale_at),
                now=NOW,
            )

    @pytest.mark.parametrize("field", ["account_id", "environment", "broker_endpoint"])
    def test_fails_closed_when_account_environment_or_endpoint_is_ambiguous(
        self, field: str
    ) -> None:
        with pytest.raises(OrderAuthorityDenied, match="ambiguous"):
            assert_order_authorized(
                OrderAuthorityMode.LIVE_CONFIRM_EACH_ORDER,
                is_live=True,
                confirmation=_fresh_confirmation(**{field: ""}),
                now=NOW,
            )

    def test_can_also_submit_a_paper_order_with_confirmation(self) -> None:
        # LIVE_CONFIRM_EACH_ORDER is not "live-only" — it's the mode that
        # additionally permits live orders; paper orders still require
        # their own confirmation under this mode too.
        assert_order_authorized(
            OrderAuthorityMode.LIVE_CONFIRM_EACH_ORDER,
            is_live=False,
            confirmation=_fresh_confirmation(),
            now=NOW,
        )


class TestBracketLegConfirmation:
    def test_primary_leg_always_needs_its_own_confirmation(self) -> None:
        assert bracket_leg_requires_its_own_confirmation("PRIMARY", primary_confirmed=True) is True

    @pytest.mark.parametrize("leg_role", ["STOP_LOSS", "TAKE_PROFIT", "TRAILING", "OCO"])
    def test_protective_legs_need_no_second_confirmation_once_primary_confirmed(
        self, leg_role: str
    ) -> None:
        assert bracket_leg_requires_its_own_confirmation(leg_role, primary_confirmed=True) is False

    @pytest.mark.parametrize("leg_role", ["STOP_LOSS", "TAKE_PROFIT", "TRAILING", "OCO"])
    def test_protective_legs_still_need_confirmation_if_primary_was_never_confirmed(
        self, leg_role: str
    ) -> None:
        assert bracket_leg_requires_its_own_confirmation(leg_role, primary_confirmed=False) is True


class TestBrokerBoundaryIsSingleEntryPoint:
    """ "Only the deterministic order service can submit, replace, or
    cancel an order" and "no LLM, Cowork task, news article, email,
    notification, or external text may directly invoke the broker
    boundary" — enforced today as a structural fact about the codebase:
    the one function that actually books a fill (`_apply_fill`) and the
    three order-mutating endpoints live in exactly one module."""

    def test_apply_fill_is_defined_and_used_only_in_orders_router(self) -> None:
        from pathlib import Path

        src_root = Path(__file__).resolve().parent.parent / "src" / "tradingos_api"
        offending: list[str] = []
        for py_file in src_root.rglob("*.py"):
            if py_file.name == "orders.py" and py_file.parent.name == "routers":
                continue
            text = py_file.read_text(encoding="utf-8")
            if "_apply_fill" in text:
                offending.append(str(py_file.relative_to(src_root)))
        assert offending == [], (
            f"_apply_fill (the order-fill/broker-boundary function) is referenced "
            f"outside routers/orders.py: {offending}"
        )

    def test_order_mutation_entrypoints_defined_only_in_orders_router(self) -> None:
        import ast
        from pathlib import Path

        routers_dir = Path(__file__).resolve().parent.parent / "src" / "tradingos_api" / "routers"
        mutating_names = {"propose_order", "confirm_order", "cancel_order", "import_fills"}
        found_elsewhere: list[str] = []
        for py_file in routers_dir.glob("*.py"):
            if py_file.name == "orders.py":
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in mutating_names:
                    found_elsewhere.append(f"{py_file.name}::{node.name}")
        assert found_elsewhere == []
