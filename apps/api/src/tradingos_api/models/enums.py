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
    """ADR-038's original 8 committee roles (`BULL`..`CIO`) are a single,
    lane-agnostic committee design that predates Revision Prompt R3's
    Investment/Tactical mode split. Revision Prompt 6 replaces that
    design with two separate, non-overlapping committees — the 8
    Investment roles and 9 Tactical roles below — per its own "the two
    workflows may share evidence, but they must not share a conclusion."
    The original 8 values are kept, unremoved, for backward compatibility
    with already-seeded fixture data; no new code writes them."""

    BULL = "BULL"
    BEAR = "BEAR"
    TECHNICAL = "TECHNICAL"
    FUNDAMENTAL = "FUNDAMENTAL"
    MACRO = "MACRO"
    RISK_MANAGER = "RISK_MANAGER"
    PORTFOLIO_MANAGER = "PORTFOLIO_MANAGER"
    CIO = "CIO"

    # Investment Committee (Revision Prompt 6) — ~3-24 month horizon.
    BUSINESS_QUALITY_ANALYST = "BUSINESS_QUALITY_ANALYST"
    FUNDAMENTAL_VALUATION_ANALYST = "FUNDAMENTAL_VALUATION_ANALYST"
    INDUSTRY_COMPETITIVE_ANALYST = "INDUSTRY_COMPETITIVE_ANALYST"
    LONG_TERM_BULL_ANALYST = "LONG_TERM_BULL_ANALYST"
    LONG_TERM_BEAR_ANALYST = "LONG_TERM_BEAR_ANALYST"
    PORTFOLIO_STRATEGIST = "PORTFOLIO_STRATEGIST"
    INVESTMENT_RISK_MANAGER = "INVESTMENT_RISK_MANAGER"
    INVESTMENT_CIO = "INVESTMENT_CIO"

    # Tactical Trading Desk (Revision Prompt 6) — ~1-10 trading day horizon.
    MARKET_INTELLIGENCE_ANALYST = "MARKET_INTELLIGENCE_ANALYST"
    TACTICAL_TECHNICAL_ANALYST = "TACTICAL_TECHNICAL_ANALYST"
    EARNINGS_GUIDANCE_ANALYST = "EARNINGS_GUIDANCE_ANALYST"
    NEWS_CATALYST_ANALYST = "NEWS_CATALYST_ANALYST"
    TACTICAL_BULL = "TACTICAL_BULL"
    TACTICAL_BEAR = "TACTICAL_BEAR"
    PORTFOLIO_CORRELATION_MANAGER = "PORTFOLIO_CORRELATION_MANAGER"
    TRADING_RISK_MANAGER = "TRADING_RISK_MANAGER"
    TRADING_CIO = "TRADING_CIO"


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


# ---------------------------------------------------------------------------
# Revision Prompt R3 — decision taxonomy, investment thesis, earnings
# evidence, morning plan, order authority, strategy governance. Additive
# to the Phase 8 schema (ADR-050) — every enum below is brand new, no
# existing enum type is altered or renamed.
# ---------------------------------------------------------------------------


class RecommendationMode(StrEnum):
    """PROJECT_INSTRUCTIONS.md v2 amendment PM-1/PM-2 (adopted R0's
    `policy/recommendation_modes.py`), now schema-backed per ADR-046:
    two rows in `recommendations`/`recommendation_versions`, distinguished
    by this column, rather than two separate tables."""

    INVESTMENT = "INVESTMENT"
    TACTICAL = "TACTICAL"


THESIS_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "ACTIVE": {"UNDER_REVIEW", "INVALIDATED", "CLOSED"},
    "UNDER_REVIEW": {"ACTIVE", "INVALIDATED", "CLOSED"},
    "INVALIDATED": {"CLOSED"},
    "CLOSED": set(),
}


class ThesisStatus(StrEnum):
    ACTIVE = "ACTIVE"
    UNDER_REVIEW = "UNDER_REVIEW"
    INVALIDATED = "INVALIDATED"
    CLOSED = "CLOSED"


class EarningsTimingCategory(StrEnum):
    """docs/HYBRID_EARNINGS_STRATEGY.md HES-2 condition 1 (verified event
    time) needs a closed vocabulary for "when," not a free-text guess.

    Revision Prompt 4 adds `TIME_NOT_SUPPLIED` (the date is confirmed but
    no session-timing was given by any source) and `DATE_UNCONFIRMED`
    (not even the date itself is verified yet) — two more precise states
    than the original `UNKNOWN`, which is kept, unremoved, for backward
    compatibility with existing rows; new ingestion code should prefer
    one of the two new values over `UNKNOWN` going forward."""

    BEFORE_OPEN = "BEFORE_OPEN"
    AFTER_CLOSE = "AFTER_CLOSE"
    DURING_MARKET = "DURING_MARKET"
    UNKNOWN = "UNKNOWN"
    TIME_NOT_SUPPLIED = "TIME_NOT_SUPPLIED"
    DATE_UNCONFIRMED = "DATE_UNCONFIRMED"


class MorningPlanVersionLabel(StrEnum):
    """docs/MORNING_PLAN_SPEC.md — PRELIMINARY (05:45) and FINAL (06:10)
    are distinct, separately-stored artifacts; AD_HOC is a manual
    "run now"; CORRECTION is a later, clearly-superseding artifact that
    never edits an already-published version in place."""

    PRELIMINARY = "PRELIMINARY"
    FINAL = "FINAL"
    AD_HOC = "AD_HOC"
    CORRECTION = "CORRECTION"


MORNING_PLAN_RUN_TRANSITIONS: dict[str, set[str]] = {
    "RUNNING": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),
    "FAILED": set(),
}


class MorningPlanRunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PlanCompletenessStatus(StrEnum):
    """docs/MORNING_PLAN_SPEC.md MDS-4 — publish INCOMPLETE rather than
    fabricate certainty."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class MorningPlanSectionKey(StrEnum):
    """The fixed section grouping, in this exact order. `HOLD_MANAGE`/
    `INVESTMENT_WATCH`/`TACTICAL_WATCH`/`AVOID` are R0/R3's original
    architecture-pass section keys, kept (not removed — a prior version
    could reference them) but superseded by Revision Prompt 9's own,
    more detailed dashboard hierarchy: `BUY_AND_HOLD` (INVEST_BUY/ADD/
    HOLD candidates with valuation/accumulation-zone/thesis-health
    detail, replacing the investment half of `HOLD_MANAGE` plus
    `INVESTMENT_WATCH`), `TACTICAL_TRADES` (eligible pre-earnings,
    wait-for-confirmation, active tactical positions, post-earnings
    confirmation status — replacing the tactical half of `HOLD_MANAGE`
    plus `TACTICAL_WATCH`), `WATCH_AND_AVOID` (near-qualified candidates,
    failed score components, and explicit avoid/no-action reasons —
    a superset of `AVOID`), and `UPCOMING_EVENTS` (the earnings calendar
    view, new). `services/morning_plan_generate.py` only ever writes the
    Revision Prompt 9 section keys."""

    ACT_NOW = "ACT_NOW"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    HOLD_MANAGE = "HOLD_MANAGE"
    INVESTMENT_WATCH = "INVESTMENT_WATCH"
    TACTICAL_WATCH = "TACTICAL_WATCH"
    AVOID = "AVOID"
    DATA_PROBLEMS = "DATA_PROBLEMS"
    BUY_AND_HOLD = "BUY_AND_HOLD"
    TACTICAL_TRADES = "TACTICAL_TRADES"
    WATCH_AND_AVOID = "WATCH_AND_AVOID"
    UPCOMING_EVENTS = "UPCOMING_EVENTS"


class DeliveryChannel(StrEnum):
    """Distinct from `NotificationChannel` (alerts) — this is specifically
    which surface received a *plan* delivery, and includes `COWORK`
    (ADR-049, read-only, off by default), which `NotificationChannel`
    doesn't need to know about."""

    IN_APP = "IN_APP"
    COWORK = "COWORK"


class OrderAuthorityMode(StrEnum):
    """Schema-backed mirror of `policy.order_authority.OrderAuthorityMode`
    (R0) — kept as a second, independent enum definition rather than a
    shared import, since `models/enums.py` defines native Postgres enum
    types and must not import from the `policy/` package (which is
    deliberately DB-agnostic, pure-Python, with no SQLAlchemy dependency
    at all — importing a model type into it, or vice versa, would blur
    that boundary). `operating_mode_history` rows use this enum; call
    sites are responsible for keeping the two enums' value sets in sync,
    checked by `tests/test_policy_order_authority.py`'s exact-four-modes
    assertion and this file's own equivalent."""

    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_MANUAL_APPROVAL = "PAPER_MANUAL_APPROVAL"
    PAPER_AUTO_POLICY = "PAPER_AUTO_POLICY"
    LIVE_CONFIRM_EACH_ORDER = "LIVE_CONFIRM_EACH_ORDER"


class EnvironmentLabel(StrEnum):
    RESEARCH = "RESEARCH"
    PAPER = "PAPER"
    LIVE = "LIVE"


ORDER_PROPOSAL_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"UNDER_EVALUATION", "WITHDRAWN"},
    "UNDER_EVALUATION": {"EVALUATED", "WITHDRAWN"},
    "EVALUATED": {"SUPERSEDED", "WITHDRAWN"},
    "SUPERSEDED": set(),
    "WITHDRAWN": set(),
}


class OrderProposalStatus(StrEnum):
    """A proposal's own lifecycle, upstream of and distinct from
    `OrderStatus` (which begins only once a proposal is approved and
    actually submitted, docs/ORDER_AUTHORITY_MODEL.md)."""

    DRAFT = "DRAFT"
    UNDER_EVALUATION = "UNDER_EVALUATION"
    EVALUATED = "EVALUATED"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"


ORDER_APPROVAL_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"APPROVED", "REJECTED", "EXPIRED", "INVALIDATED"},
    "APPROVED": {"INVALIDATED"},
    "REJECTED": set(),
    "EXPIRED": set(),
    "INVALIDATED": set(),
}


class OrderApprovalStatus(StrEnum):
    """`EXPIRED`/`INVALIDATED` are terminal and, once reached, can never
    transition back to `APPROVED` — docs/ORDER_AUTHORITY_MODEL.md's
    approval-binding section and this revision's required test ("expired
    approval cannot return an approved state")."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class ApprovalInvalidationReason(StrEnum):
    PRICE_MOVED = "PRICE_MOVED"
    EXPIRED = "EXPIRED"
    MANUAL = "MANUAL"
    AMBIGUOUS_IDENTITY = "AMBIGUOUS_IDENTITY"
    KILL_SWITCH = "KILL_SWITCH"
    BOUND_FIELD_CHANGED = "BOUND_FIELD_CHANGED"


class BrokerSubmissionOutcome(StrEnum):
    """`SUCCEEDED` exists in the vocabulary for schema completeness, but no
    code path in this revision ever writes it for a `LIVE` environment —
    "do not add a live broker submission endpoint yet" (Revision Prompt
    R3). Revision Prompt 10 adds `TIMEOUT_UNKNOWN` — a submit call whose
    HTTP response never arrived, so this attempt's own outcome is
    genuinely unknown until a status query resolves it one way or the
    other (never assumed FAILED, which would risk a duplicate resubmit;
    never assumed SUCCEEDED, which would risk fabricating a fill)."""

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DENIED = "DENIED"
    TIMEOUT_UNKNOWN = "TIMEOUT_UNKNOWN"


class StrategyFamily(StrEnum):
    """Classifies an existing `strategy_definitions` row by which decision
    workflow it governs — additive column, not a new table, since a
    strategy definition already has exactly one family for its lifetime."""

    INVESTMENT_QUALITY = "INVESTMENT_QUALITY"
    EARNINGS_PRE_EVENT = "EARNINGS_PRE_EVENT"
    EARNINGS_POST_CONFIRMATION = "EARNINGS_POST_CONFIRMATION"
    GENERIC = "GENERIC"


# ---------------------------------------------------------------------------
# Revision Prompt 5 — deterministic dual-lane analytics and earnings
# feature engine (additive to Phase 8/R3/R4).
# ---------------------------------------------------------------------------


class FeatureComponentStatus(StrEnum):
    """The per-component outcome `models.feature_scoring.FeatureComponentResult`
    rows carry (the diagnostic UI's required "pass/fail ... missing
    state" per component). `CAPABILITY_UNAVAILABLE` is distinct from
    `MISSING_DATA`: the former means this data entitlement can never
    supply the input (e.g. 30-minute intraday range without a real-time
    feed) — a structural limit, not a transient gap — so a caller can
    tell "we don't have this feed" from "the feed had nothing today."
    `INSUFFICIENT_HISTORY` is distinct from both: `services/analytics.py`
    and the tactical 8-component score report it when the input series
    is simply too short for the window requested (e.g. fewer than 2
    prior earnings gaps for `PRIOR_GAP_BIAS`) — the data exists and
    isn't capability-gated, there just isn't enough of it yet. Never
    silently treated as `FAIL` (principle 4/5 — missing evidence is
    shown explicitly, not defaulted to failing)."""

    PASS = "PASS"
    FAIL = "FAIL"
    MISSING_DATA = "MISSING_DATA"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


# ---------------------------------------------------------------------------
# Revision Prompt 8 — portfolio, lane attribution, trade journal, and
# reconciliation (additive to Phase 8/R3).
# ---------------------------------------------------------------------------


class LotLane(StrEnum):
    """Every `PositionLot` gets exactly one of these — "attribute every
    new lot," not "attribute the ones that came with a clear enough
    recommendation." `UNCLASSIFIED` is a first-class, queryable state
    (e.g. a manual fill entered with no linked recommendation), never a
    `NULL` a caller has to remember to treat specially. Deliberately a
    separate enum from `RecommendationMode` (INVESTMENT/TACTICAL only)
    rather than reusing it with a nullable column — a lot's lane and a
    recommendation's lane are different concepts that happen to share
    two of three values; `UNCLASSIFIED` has no recommendation-mode
    analog at all."""

    INVESTMENT = "INVESTMENT"
    TACTICAL = "TACTICAL"
    UNCLASSIFIED = "UNCLASSIFIED"


class JournalExitReason(StrEnum):
    """Why a `Trade` closed — one explicit reason, not inferred after the
    fact from price action alone."""

    STOP_HIT = "STOP_HIT"
    TARGET_HIT = "TARGET_HIT"
    TIME_EXIT = "TIME_EXIT"
    THESIS_BROKEN = "THESIS_BROKEN"
    TRAILING_STOP = "TRAILING_STOP"
    POST_CONFIRMATION_FAILED = "POST_CONFIRMATION_FAILED"
    MANUAL_EXIT = "MANUAL_EXIT"
    OTHER = "OTHER"


class ImportRowStatus(StrEnum):
    """Per-row outcome of a CSV import — "import idempotency" requires a
    re-imported row that already exists be visibly `DUPLICATE_SKIPPED`,
    not silently absent from the result."""

    IMPORTED = "IMPORTED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"
    ERROR = "ERROR"


class ReconciliationStatus(StrEnum):
    MATCHED = "MATCHED"
    DISCREPANCY = "DISCREPANCY"


class KillSwitchBehavior(StrEnum):
    """Revision Prompt 10 — one of the fields a `PAPER_AUTO_POLICY` grant
    must explicitly choose: what an *automatic* submission path does
    when the (always-authoritative) global kill switch is active.
    `HALT_NEW_ONLY` stops the policy from generating new automatic
    submissions but leaves whatever it already has open at the broker
    alone; `HALT_AND_CANCEL_OPEN` additionally cancels every open order
    this policy itself submitted. This is a *policy-scoped* preference,
    never the kill switch's own behavior — the kill switch itself always
    invalidates every pending approval regardless of this setting
    (OA-9); this only governs the auto-policy's own already-open orders,
    the "separate action" the architecture doc calls "cancel-open-orders"
    scoped to what one policy is responsible for."""

    HALT_NEW_ONLY = "HALT_NEW_ONLY"
    HALT_AND_CANCEL_OPEN = "HALT_AND_CANCEL_OPEN"
