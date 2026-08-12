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
- `POST /api/v1/ask` (`routers/ask.py`/`services/ask.py`/
  `services/ask_tools.py`) — the LLM tool-use endpoint originally
  retired in the "Phase 8" commit and rebuilt during end-to-end platform
  testing against the current schema (ADR-019). Its own design already
  makes it read-only (`services/ask_tools.py`'s docstring: "none of
  these tools write anything ... `/ask` only ever reads"), but the
  original retirement note here said exactly this — "so a future
  re-introduction ... knows to add itself to this test, not skip it" —
  so it's proven the same structural way the Cowork path is, not just
  asserted in a docstring.

These are import-level and text-level checks on the specific files named
above (not the whole `src/` tree) — the broader "only orders.py defines
the mutating entrypoints" fact is already proven elsewhere; this file
proves each read-only surface never reaches for them.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROUTERS_DIR = Path(__file__).resolve().parent.parent / "src" / "tradingos_api" / "routers"
_SERVICES_DIR = Path(__file__).resolve().parent.parent / "src" / "tradingos_api" / "services"

MORNING_PLAN_ROUTER = _ROUTERS_DIR / "morning_plan.py"
ASK_ROUTER = _ROUTERS_DIR / "ask.py"
ASK_SERVICE = _SERVICES_DIR / "ask.py"
ASK_TOOLS_SERVICE = _SERVICES_DIR / "ask_tools.py"

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


class TestAskEndpointHasNoWriteCapability:
    """`/ask` was rebuilt during end-to-end platform testing (ADR-019) —
    this proves it stayed read-only the same structural way
    `TestCoworkDeliveryPathHasNoWriteCapability` proves it for the
    Cowork brief, across all three files the request actually touches
    (`routers/ask.py` → `services/ask.py` → `services/ask_tools.py`)."""

    def test_ask_modules_import_no_state_changing_module(self) -> None:
        for path in (ASK_ROUTER, ASK_SERVICE, ASK_TOOLS_SERVICE):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = _imported_module_names(tree)
            offending = [
                module
                for module in imported
                if any(module.startswith(prefix) for prefix in _FORBIDDEN_MODULE_PREFIXES)
            ]
            assert offending == [], (
                f"{path.name} (the /ask read-only NL-query path) imports from "
                f"state-changing module(s): {offending}"
            )

    def test_ask_modules_never_reference_a_mutating_function_name(self) -> None:
        for path in (ASK_ROUTER, ASK_SERVICE, ASK_TOOLS_SERVICE):
            text = path.read_text(encoding="utf-8")
            offending = sorted(name for name in _FORBIDDEN_NAMES if name in text)
            assert offending == [], (
                f"{path.name} references order/approval/kill-switch mutating "
                f"function name(s): {offending}"
            )

    def test_ask_endpoint_is_a_post_route(self) -> None:
        """`/ask` is intentionally a POST (it's an LLM call with a request
        body, not a bare resource fetch) — that alone doesn't make it
        state-changing; the two checks above are what actually prove
        that. This just pins the route's shape so a future change is
        deliberate, not accidental."""
        tree = ast.parse(ASK_ROUTER.read_text(encoding="utf-8"))
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "ask":
                found = True
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(
                        decorator.func, ast.Attribute
                    ):
                        assert decorator.func.attr == "post", (
                            f"ask() is decorated with @router.{decorator.func.attr}, "
                            "not @router.post."
                        )
        assert found, "ask() not found in routers/ask.py"
