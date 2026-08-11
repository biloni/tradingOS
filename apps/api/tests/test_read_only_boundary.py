"""Structural proof that the app's read-only delivery paths have no
code path into order/approval/mode-change services (Revision Prompt 16,
ADR-066's own stated follow-up; extends the existing broker-boundary
proof in tests/test_policy_order_authority.py::TestBrokerBoundaryIsSingleEntryPoint,
which only covers orders.py's own mutating functions).

Two read-only surfaces exist in the current codebase:
- `GET /api/v1/morning-plan/cowork-brief` (`routers/morning_plan.py`) —
  the Cowork scheduled-task delivery contract (SS-5, ADR-049): read-only
  by design, and the one channel PROJECT_INSTRUCTIONS.md's v2 amendment
  names explicitly as non-exempt from this rule.
- The `/ask` LLM tool-use endpoint was retired in the "Phase 8" commit
  (docs/SECURITY.md's v2 amendment section already documents this) —
  there is no backend route left to check; noted here so a future
  re-introduction of an `/ask`-equivalent NL-query feature knows to add
  itself to this test, not skip it.

These are import-level and text-level checks on `routers/morning_plan.py`
specifically (not the whole `src/` tree) — the broader "only orders.py
defines the mutating entrypoints" fact is already proven elsewhere;
this file proves the read-only router never reaches for them.
"""

from __future__ import annotations

import ast
from pathlib import Path

MORNING_PLAN_ROUTER = (
    Path(__file__).resolve().parent.parent / "src" / "tradingos_api" / "routers" / "morning_plan.py"
)

# Modules that own state-changing order/approval/kill-switch/mode-change
# capability — a read-only delivery router must never import from any
# of these.
_FORBIDDEN_MODULE_PREFIXES = (
    "tradingos_api.routers.orders",
    "tradingos_api.routers.order_authority",
    "tradingos_api.routers.settings",
    "tradingos_api.routers.paper_auto_policy",
    "tradingos_api.services.order_execution",
    "tradingos_api.services.order_authority",
    "tradingos_api.services.paper_auto_policy",
)

# The mutating function names themselves — a text-level check that
# catches a local re-implementation, not just a missing import.
_FORBIDDEN_NAMES = {
    "_apply_fill",
    "propose_order",
    "confirm_order",
    "cancel_order",
    "import_fills",
    "activate_kill_switch",
    "deactivate_kill_switch",
    "cancel_open_orders",
    "approve_order_approval",
    "reject_order_approval",
    "submit_order_approval",
    "submit_paper_order",
}


def _imported_module_names(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


class TestCoworkDeliveryPathHasNoWriteCapability:
    def test_morning_plan_router_imports_no_state_changing_module(self) -> None:
        tree = ast.parse(MORNING_PLAN_ROUTER.read_text(encoding="utf-8"))
        imported = _imported_module_names(tree)
        offending = [
            module
            for module in imported
            if any(module.startswith(prefix) for prefix in _FORBIDDEN_MODULE_PREFIXES)
        ]
        assert offending == [], (
            f"routers/morning_plan.py (the Cowork read-only delivery contract) imports "
            f"from state-changing module(s): {offending}"
        )

    def test_morning_plan_router_never_references_a_mutating_function_name(self) -> None:
        text = MORNING_PLAN_ROUTER.read_text(encoding="utf-8")
        offending = sorted(name for name in _FORBIDDEN_NAMES if name in text)
        assert offending == [], (
            f"routers/morning_plan.py references order/approval/kill-switch "
            f"mutating function name(s): {offending}"
        )

    def test_cowork_brief_endpoint_is_a_get_route(self) -> None:
        """Belt-and-suspenders: the contract itself must be a GET, not
        just "happens not to call a mutating function today"."""
        tree = ast.parse(MORNING_PLAN_ROUTER.read_text(encoding="utf-8"))
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_cowork_brief":
                found = True
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(
                        decorator.func, ast.Attribute
                    ):
                        assert decorator.func.attr == "get", (
                            f"get_cowork_brief is decorated with @router.{decorator.func.attr}, "
                            "not @router.get — the Cowork delivery contract must stay read-only."
                        )
        assert found, "get_cowork_brief not found in routers/morning_plan.py"


class TestAskEndpointIsRetiredNotJustUnrouted:
    """`/ask` (services/ask.py, routers/ask.py) was deleted in Phase 8 —
    confirmed absent here so this fact stays structurally checked rather
    than only asserted in a docs comment that can drift."""

    def test_no_ask_router_module_exists(self) -> None:
        routers_dir = MORNING_PLAN_ROUTER.parent
        assert not (routers_dir / "ask.py").exists()

    def test_no_ask_service_module_exists(self) -> None:
        services_dir = MORNING_PLAN_ROUTER.parent.parent / "services"
        assert not (services_dir / "ask.py").exists()
