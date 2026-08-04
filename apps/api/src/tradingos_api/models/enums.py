"""Central enum registry for the Phase 8 domain model (ADR-043).

Every lifecycle-bearing enum across all bounded contexts is defined here,
in one place, specifically so the *set* of valid states and the *map* of
valid transitions between them can be reviewed together rather than
scattered across ~30 model files — the refinement brief's "define
lifecycle enums carefully and enforce valid transitions in domain
services" is easiest to actually honor when the enums are centralized and
the transition maps sit right next to them.

Non-lifecycle enums (closed sets that don't have a state machine — e.g.
`OrderSide`, `AgentRole`) live here too, for the same discoverability
reason, even though they don't get a transition map.

`services/lifecycle.py` provides the one generic `assert_transition_allowed()`
helper every domain service should call before writing a status change.
This pass wires it up for the two lifecycles with real ported business
logic (`OrderStatus`, from the existing paper-order flow; `RecommendationStatus`,
from the existing recommendation-supersession flow). The remaining
lifecycles below (`AgentRunStatus`, `CommitteeSessionStatus`,
`ModelChangeProposalStatus`, `AlertStatus`, `JobRunStatus`) get their enum
and transition map defined now, ready for the future orchestration phases
(committee execution, model-change governance, alerting) that actually
drive those transitions — this pass only builds the schema/API layer for
them (per its own scope: "domain model ... do not integrate external
providers yet"), not their business logic.
"""

from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# Identity & preferences
# ---------------------------------------------------------------------------


class RiskTolerance(StrEnum):
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class ProviderKind(StrEnum):
    MARKET_DATA = "MARKET_DATA"
    BROKER = "BROKER"
    LLM = "LLM"
    NEWS = "NEWS"
    FUNDAMENTALS = "FUNDAMENTALS"


class NotificationChannel(StrEnum):
    """Only IN_APP is actually usable today (BLOCKING_DECISIONS.md #9) —
    the others exist so `notification_preferences` doesn't need a schema
    change if a future phase adds a delivery channel."""

    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"


# ---------------------------------------------------------------------------
# Security master & watchlists
# ---------------------------------------------------------------------------


class AssetType(StrEnum):
    """Market universe is equities + ETFs only for the MVP (ADR-003)."""

    EQUITY = "EQUITY"
    ETF = "ETF"


class InstrumentValidationStatus(StrEnum):
    """ADR-032 — never silently assume a raw ticker string is tradable."""

    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    QUARANTINED = "QUARANTINED"


class MonitoringFrequency(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    INTRADAY = "INTRADAY"


# ---------------------------------------------------------------------------
# Market evidence
# ---------------------------------------------------------------------------


class Timeframe(StrEnum):
    DAILY = "DAILY"
    INTRADAY_5MIN = "INTRADAY_5MIN"
    INTRADAY_15MIN = "INTRADAY_15MIN"
    INTRADAY_60MIN = "INTRADAY_60MIN"


class CorporateActionType(StrEnum):
    SPLIT = "SPLIT"
    DIVIDEND = "DIVIDEND"
    SPINOFF = "SPINOFF"
    MERGER = "MERGER"


class DataQualityStatus(StrEnum):
    """Principle 5: missing/stale/conflicting/delayed data must be shown
    explicitly, never silently backfilled."""

    OK = "OK"
    STALE = "STALE"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"
    DELAYED = "DELAYED"


class EarningsRevisionDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    UNCHANGED = "UNCHANGED"


class RegimeClassification(StrEnum):
    """ADR-034 — feeds risk budget only, never an independent buy trigger."""

    CALM = "CALM"
    ELEVATED = "ELEVATED"
    STRESSED = "STRESSED"


# ---------------------------------------------------------------------------
# Agent & recommendation
# ---------------------------------------------------------------------------


class AgentRole(StrEnum):
    """ADR-038's 8 committee roles."""

    BULL = "BULL"
    BEAR = "BEAR"
    TECHNICAL = "TECHNICAL"
    FUNDAMENTAL = "FUNDAMENTAL"
    MACRO = "MACRO"
    RISK_MANAGER = "RISK_MANAGER"
    PORTFOLIO_MANAGER = "PORTFOLIO_MANAGER"
    CIO = "CIO"


AGENT_RUN_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"RUNNING"},
    "RUNNING": {"SUCCEEDED", "FAILED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
}


class AgentRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


COMMITTEE_SESSION_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"RUNNING"},
    "RUNNING": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),
    "FAILED": set(),
}


class CommitteeSessionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RecommendationAction(StrEnum):
    """FR-27 — six-state output, replacing the shipped MVP's score-only
    shape. `NO_ACTION` and cash are always valid outputs (FR-25)."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WATCH = "WATCH"
    AVOID = "AVOID"
    NO_ACTION = "NO_ACTION"


class RecommendationLevelKind(StrEnum):
    ENTRY = "ENTRY"
    STOP = "STOP"
    TARGET = "TARGET"
    TRAILING = "TRAILING"


RECOMMENDATION_TRANSITIONS: dict[str, set[str]] = {
    "ACTIVE": {"SUPERSEDED", "EXPIRED", "CANCELED"},
    "SUPERSEDED": set(),
    "EXPIRED": set(),
    "CANCELED": set(),
}


class RecommendationStatus(StrEnum):
    """Extends the shipped MVP's ACTIVE/SUPERSEDED with two more terminal
    states a six-action, evidence-driven recommendation actually needs:
    EXPIRED (the evidence window lapsed without the user acting) and
    CANCELED (invalidated before expiry, e.g. a data-quality retraction)."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    CANCELED = "CANCELED"


class RecommendationConfidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ---------------------------------------------------------------------------
# Portfolio & execution
# ---------------------------------------------------------------------------


class AccountType(StrEnum):
    """ADR-039 — the journal (MANUAL) is the primary tracked portfolio;
    PAPER_ALPACA is the existing Alpaca paper-broker sandbox, now modeled
    as one row in this shared table rather than its own bespoke schema."""

    MANUAL = "MANUAL"
    PAPER_ALPACA = "PAPER_ALPACA"


class CashLedgerEntryType(StrEnum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRADE_DEBIT = "TRADE_DEBIT"
    TRADE_CREDIT = "TRADE_CREDIT"
    FEE = "FEE"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(StrEnum):
    DAY = "DAY"
    GTC = "GTC"


ORDER_TRANSITIONS: dict[str, set[str]] = {
    # FILLED is reachable directly from DRAFT for MANUAL accounts, whose
    # "confirm" has no broker submission step — see routers/orders.py::confirm_order.
    "DRAFT": {"SUBMITTED", "FILLED", "CANCELED"},
    "SUBMITTED": {"PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"},
    "PARTIALLY_FILLED": {"FILLED", "CANCELED"},
    "FILLED": set(),
    "CANCELED": set(),
    "REJECTED": set(),
    "EXPIRED": set(),
}


class OrderStatus(StrEnum):
    """Extends the shipped MVP's `PaperOrderStatus` with `EXPIRED` (a
    day-only order that never filled) — everything else carries over
    unchanged in meaning (ADR-014's DRAFT-until-confirmed gate, principle
    11, is unchanged)."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderLegRole(StrEnum):
    """Models bracket/OCO relationships (a primary entry plus a protective
    stop-loss and/or a take-profit leg) without assuming every account's
    broker actually supports native bracket orders — a manual account has
    no broker to support anything, so the *relationship* is modeled in our
    own schema (`order_legs.parent_order_id` + `role`) regardless of
    whether any downstream broker call ever groups them."""

    PRIMARY = "PRIMARY"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class FeeType(StrEnum):
    COMMISSION = "COMMISSION"
    SEC_FEE = "SEC_FEE"
    TAF = "TAF"
    OTHER = "OTHER"


class TradeStatus(StrEnum):
    """A `trades`/round-trip row spans one or more executions from the
    first opening fill to the position returning to flat."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


# ---------------------------------------------------------------------------
# Outcomes & learning
# ---------------------------------------------------------------------------


class RecommendationOutcomeClassification(StrEnum):
    """ADR-041 — computed from journal/order matching, never self-reported."""

    FOLLOWED = "FOLLOWED"
    IGNORED = "IGNORED"
    MODIFIED = "MODIFIED"


class TradeReviewRating(StrEnum):
    GOOD_PROCESS = "GOOD_PROCESS"
    NEUTRAL = "NEUTRAL"
    POOR_PROCESS = "POOR_PROCESS"


STRATEGY_VERSION_TRANSITIONS: dict[str, set[str]] = {
    "PROPOSED": {"ACTIVE", "REJECTED"},
    "ACTIVE": {"SUPERSEDED"},
    "REJECTED": set(),
    "SUPERSEDED": set(),
}


class StrategyVersionStatus(StrEnum):
    """Unchanged in meaning from the shipped MVP (ADR-027) — now a version
    row under a `strategy_definitions` parent (ADR-043) rather than a
    standalone table, principle 16's gate mechanism is otherwise identical."""

    PROPOSED = "PROPOSED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class BacktestTradeExitReason(StrEnum):
    SIGNAL_EXIT = "SIGNAL_EXIT"
    MAX_HOLDING_DAYS = "MAX_HOLDING_DAYS"
    END_OF_BACKTEST = "END_OF_BACKTEST"


MODEL_CHANGE_PROPOSAL_TRANSITIONS: dict[str, set[str]] = {
    "PROPOSED": {"APPROVED", "REJECTED", "WITHDRAWN"},
    "APPROVED": set(),
    "REJECTED": set(),
    "WITHDRAWN": set(),
}


class ModelChangeProposalStatus(StrEnum):
    """Principle 16, generalized beyond scoring weights (FR-46: a prompt
    change is a strategy change like any other) — `strategy_versions`
    covers numeric-threshold changes; this covers everything else a future
    governance UI might route through the same review discipline (e.g. an
    agent prompt version bump, a committee pre-filter bar change)."""

    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


ALERT_TRANSITIONS: dict[str, set[str]] = {
    "OPEN": {"ACKNOWLEDGED", "DISMISSED"},
    "ACKNOWLEDGED": {"DISMISSED"},
    "DISMISSED": set(),
}


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"


class AlertDeliveryStatus(StrEnum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


JOB_RUN_TRANSITIONS: dict[str, set[str]] = {
    "RUNNING": {"SUCCEEDED", "FAILED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
}


class JobRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class PromptTemplateStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
