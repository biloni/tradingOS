"""Phase 8 seed fixtures: `uv run tradingos-seed` (or `uv run python -m
tradingos_api.scripts.seed_phase8`).

Populates one representative, synthetic example of every bounded context in
the new domain model — enough for every new `/api/v1/*` endpoint to return
real, coherent data without any live provider call ("do not integrate
external providers yet"). Deterministic (no RNG), idempotent (a no-op if a
`UserProfile` row already exists — matching the shipped MVP's single-guard
idempotency style rather than per-row upserts across ~40 tables).

Tier 1 watchlist: the exact 48-symbol list from the refinement brief.
Validation outcomes are **simulated** here (no real Alpaca call this
pass) — `SKHY`, `SPCX`, `NASA`, `DRAM` are deliberately quarantined with a
real-sounding reason, exactly demonstrating ADR-032's workflow; the other
44 resolve to real, named instruments.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import SessionLocal
from tradingos_api.models.agents import (
    AgentDefinition,
    AgentEvidenceLink,
    AgentOpinion,
    AgentRun,
    AgentVersion,
    CommitteeSession,
)
from tradingos_api.models.backtest import BacktestRun, BacktestTrade
from tradingos_api.models.enums import (
    AccountType,
    AgentRole,
    AgentRunStatus,
    AlertDeliveryStatus,
    AlertSeverity,
    AlertStatus,
    AssetType,
    BacktestTradeExitReason,
    CashLedgerEntryType,
    CommitteeSessionStatus,
    DataQualityStatus,
    DeliveryChannel,
    EarningsTimingCategory,
    EnvironmentLabel,
    FeeType,
    InstrumentValidationStatus,
    JobRunStatus,
    ModelChangeProposalStatus,
    MonitoringFrequency,
    MorningPlanRunStatus,
    MorningPlanSectionKey,
    MorningPlanVersionLabel,
    NotificationChannel,
    OrderApprovalStatus,
    OrderAuthorityMode,
    OrderLegRole,
    OrderProposalStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    PlanCompletenessStatus,
    PromptTemplateStatus,
    ProviderKind,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationLevelKind,
    RecommendationMode,
    RecommendationOutcomeClassification,
    RecommendationStatus,
    RegimeClassification,
    RiskTolerance,
    StrategyFamily,
    StrategyVersionStatus,
    ThesisStatus,
    Timeframe,
    TimeInForce,
    TradeReviewRating,
    TradeStatus,
)
from tradingos_api.models.execution import (
    Account,
    CashLedgerEntry,
    Execution,
    Fee,
    Order,
    OrderLeg,
    PortfolioSnapshot,
    Position,
    PositionLot,
    RiskSnapshot,
    Trade,
    TradeNote,
    TradeThesis,
)
from tradingos_api.models.identity import (
    InvestmentProfile,
    NotificationPreference,
    ProviderConfig,
    RiskPolicy,
    RiskPolicyVersion,
    UserProfile,
)
from tradingos_api.models.investment_thesis import (
    InvestmentThesis,
    InvestmentThesisVersion,
    ThesisCatalyst,
    ThesisRisk,
    ThesisStatusHistory,
    ValuationSnapshot,
)
from tradingos_api.models.learning import (
    BenchmarkSnapshot,
    DecisionPolicyVersion,
    HypotheticalTradeOutcome,
    ModelChangeApproval,
    ModelChangeProposal,
    PerformanceSnapshot,
    RecommendationOutcome,
    ScoringWeightVersion,
    StrategyDefinition,
    StrategyEligibilitySnapshot,
    StrategyVersion,
    TradeReview,
)
from tradingos_api.models.market_evidence import (
    DataQualityEvent,
    EarningsActual,
    EarningsConsensusSnapshot,
    EarningsEvent,
    EarningsFeatureSnapshot,
    EarningsGuidanceItem,
    EventExpectedMoveSnapshot,
    FundamentalsSnapshot,
    MacroObservation,
    MarketBar,
    MarketRegimeSnapshot,
    NewsItem,
    NewsItemInstrument,
    PostEarningsConfirmationSnapshot,
    SentimentSnapshot,
    TechnicalIndicatorSnapshot,
)
from tradingos_api.models.morning_plan import (
    MorningPlanDeliveryEvent,
    MorningPlanItem,
    MorningPlanQualityCheck,
    MorningPlanRun,
    MorningPlanSection,
    MorningPlanVersion,
)
from tradingos_api.models.operations import (
    Alert,
    AlertDelivery,
    JobRun,
    ModelCallRecord,
    PromptTemplate,
    PromptVersion,
)
from tradingos_api.models.order_authority import (
    ApprovalBoundFields,
    BrokerEnvironmentAttestation,
    ExecutionKillSwitchEvent,
    OperatingModeHistory,
    OrderApproval,
    OrderPolicyEvaluation,
    OrderProposal,
    OrderProposalVersion,
)
from tradingos_api.models.recommendations import (
    ConfidenceCalibrationRecord,
    Recommendation,
    RecommendationAttribution,
    RecommendationInvalidationCondition,
    RecommendationLevel,
    RecommendationStatusEvent,
    RecommendationVersion,
)
from tradingos_api.models.security_master import (
    Industry,
    Instrument,
    InstrumentValidationEvent,
    Sector,
    Watchlist,
    WatchlistItem,
)
from tradingos_api.policy.recommendation_modes import InvestmentAction, TacticalAction
from tradingos_api.services.order_authority import BoundFieldsSnapshot, compute_bound_fields_hash

TODAY = date(2026, 8, 3)
NOW = datetime(2026, 8, 3, 13, 0, tzinfo=UTC)

# ticker -> (name, exchange, asset_type, sector, industry, speculative)
TIER1_RESOLVED: dict[str, tuple[str, str, AssetType, str, str, bool]] = {
    "ALAB": (
        "Astera Labs, Inc.",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Semiconductors",
        False,
    ),
    "MRVL": (
        "Marvell Technology, Inc.",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Semiconductors",
        False,
    ),
    "ARM": ("Arm Holdings plc", "NASDAQ", AssetType.EQUITY, "Technology", "Semiconductors", False),
    "IONQ": ("IonQ, Inc.", "NYSE", AssetType.EQUITY, "Technology", "Quantum Computing", True),
    "QBTS": (
        "D-Wave Quantum Inc.",
        "NYSE",
        AssetType.EQUITY,
        "Technology",
        "Quantum Computing",
        True,
    ),
    "ON": (
        "ON Semiconductor Corporation",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Semiconductors",
        False,
    ),
    "NXPI": (
        "NXP Semiconductors N.V.",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Semiconductors",
        False,
    ),
    "ADI": (
        "Analog Devices, Inc.",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Semiconductors",
        False,
    ),
    "AMAT": (
        "Applied Materials, Inc.",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Semiconductor Equipment",
        False,
    ),
    "SNDK": (
        "Sandisk Corporation",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Semiconductors",
        False,
    ),
    "WDC": (
        "Western Digital Corporation",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Data Storage",
        False,
    ),
    "LRCX": (
        "Lam Research Corporation",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Semiconductor Equipment",
        False,
    ),
    "AVGO": ("Broadcom Inc.", "NASDAQ", AssetType.EQUITY, "Technology", "Semiconductors", False),
    "VOO": ("Vanguard S&P 500 ETF", "NYSEARCA", AssetType.ETF, "ETF", "Broad Market", False),
    "XOM": ("Exxon Mobil Corporation", "NYSE", AssetType.EQUITY, "Energy", "Oil & Gas", False),
    "WPM": (
        "Wheaton Precious Metals Corp.",
        "NYSE",
        AssetType.EQUITY,
        "Materials",
        "Precious Metals",
        False,
    ),
    "TSM": (
        "Taiwan Semiconductor Manufacturing Co.",
        "NYSE",
        AssetType.EQUITY,
        "Technology",
        "Semiconductors",
        False,
    ),
    "BE": (
        "Bloom Energy Corporation",
        "NYSE",
        AssetType.EQUITY,
        "Industrials",
        "Clean Energy",
        True,
    ),
    "PLTR": (
        "Palantir Technologies Inc.",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Software",
        True,
    ),
    "MRK": ("Merck & Co., Inc.", "NYSE", AssetType.EQUITY, "Healthcare", "Pharmaceuticals", False),
    "AMZN": ("Amazon.com, Inc.", "NASDAQ", AssetType.EQUITY, "Technology", "E-Commerce", False),
    "GOOG": ("Alphabet Inc.", "NASDAQ", AssetType.EQUITY, "Technology", "Internet", False),
    "AMD": (
        "Advanced Micro Devices, Inc.",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Semiconductors",
        False,
    ),
    "AAPL": ("Apple Inc.", "NASDAQ", AssetType.EQUITY, "Technology", "Hardware", False),
    "SPY": ("SPDR S&P 500 ETF Trust", "NYSEARCA", AssetType.ETF, "ETF", "Broad Market", False),
    "IBIT": ("iShares Bitcoin Trust", "NASDAQ", AssetType.ETF, "ETF", "Crypto", True),
    "JPM": ("JPMorgan Chase & Co.", "NYSE", AssetType.EQUITY, "Financials", "Banks", False),
    "EXPE": ("Expedia Group, Inc.", "NASDAQ", AssetType.EQUITY, "Consumer", "Travel", False),
    "CRM": ("Salesforce, Inc.", "NYSE", AssetType.EQUITY, "Technology", "Software", False),
    "TER": (
        "Teradyne, Inc.",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Semiconductor Equipment",
        False,
    ),
    "RDDT": ("Reddit, Inc.", "NYSE", AssetType.EQUITY, "Technology", "Internet", True),
    "VST": ("Vistra Corp.", "NYSE", AssetType.EQUITY, "Utilities", "Power Generation", False),
    "TSLA": ("Tesla, Inc.", "NASDAQ", AssetType.EQUITY, "Consumer", "Auto", True),
    "NOW": ("ServiceNow, Inc.", "NYSE", AssetType.EQUITY, "Technology", "Software", False),
    "BAC": ("Bank of America Corporation", "NYSE", AssetType.EQUITY, "Financials", "Banks", False),
    "OKTA": ("Okta, Inc.", "NASDAQ", AssetType.EQUITY, "Technology", "Software", True),
    "LLY": (
        "Eli Lilly and Company",
        "NYSE",
        AssetType.EQUITY,
        "Healthcare",
        "Pharmaceuticals",
        False,
    ),
    "UBER": (
        "Uber Technologies, Inc.",
        "NYSE",
        AssetType.EQUITY,
        "Technology",
        "Transportation",
        False,
    ),
    "URA": ("Global X Uranium ETF", "NYSEARCA", AssetType.ETF, "ETF", "Sector", True),
    "CVX": ("Chevron Corporation", "NYSE", AssetType.EQUITY, "Energy", "Oil & Gas", False),
    "SMCI": (
        "Super Micro Computer, Inc.",
        "NASDAQ",
        AssetType.EQUITY,
        "Technology",
        "Hardware",
        True,
    ),
    "SNOW": ("Snowflake Inc.", "NYSE", AssetType.EQUITY, "Technology", "Software", True),
    "WDAY": ("Workday, Inc.", "NASDAQ", AssetType.EQUITY, "Technology", "Software", False),
}

TIER1_QUARANTINED: dict[str, str] = {
    "SKHY": (
        "No matching active listing found on the configured reference source (Alpaca assets)."
    ),
    "SPCX": (
        "SpaceX is not a publicly listed company; no matching active equity or ETF symbol exists."
    ),
    "NASA": (
        "NASA is a U.S. government agency, not a tradable security — no matching listing exists."
    ),
    "DRAM": (
        "No matching active listing found; this does not resolve to a single tradable instrument."
    ),
}

AGENT_ROLE_NAMES: dict[AgentRole, str] = {
    AgentRole.BULL: "Bull Analyst",
    AgentRole.BEAR: "Bear Analyst",
    AgentRole.TECHNICAL: "Technical Analyst",
    AgentRole.FUNDAMENTAL: "Fundamental Analyst",
    AgentRole.MACRO: "Macro Strategist",
    AgentRole.RISK_MANAGER: "Risk Manager",
    AgentRole.PORTFOLIO_MANAGER: "Portfolio Manager",
    AgentRole.CIO: "CIO / Judge",
}


def _seed_identity(db: Session) -> UserProfile:
    user = UserProfile(display_name="Personal Trader", timezone="America/New_York")
    db.add(user)
    db.flush()

    db.add(
        InvestmentProfile(
            owner_user_id=user.id,
            starting_capital_usd=Decimal("10000.000000"),
            risk_tolerance=RiskTolerance.AGGRESSIVE,
            holding_period_min_days=2,
            holding_period_max_days=10,
        )
    )
    db.add(RiskPolicy(owner_user_id=user.id))
    for category in ("ALERT", "PREMARKET_PLAN", "EOD_REVIEW"):
        db.add(
            NotificationPreference(
                owner_user_id=user.id,
                channel=NotificationChannel.IN_APP,
                category=category,
                enabled=True,
            )
        )
    db.add(
        ProviderConfig(
            provider_kind=ProviderKind.MARKET_DATA,
            provider_name="Alpaca Markets",
            is_enabled=True,
            config_metadata={"base_url": "https://data.alpaca.markets"},
        )
    )
    db.add(
        ProviderConfig(
            provider_kind=ProviderKind.LLM,
            provider_name="Anthropic Claude",
            is_enabled=True,
            config_metadata={"model": "claude-sonnet-5"},
        )
    )
    return user


def _seed_security_master(
    db: Session, user: UserProfile
) -> tuple[dict[str, Sector], dict[str, Instrument], Watchlist, dict[str, WatchlistItem]]:
    sector_rows: dict[str, Sector] = {}
    industry_rows: dict[tuple[str, str], Industry] = {}
    for _t, (_n, _e, _a, sector_name, _i, _s) in TIER1_RESOLVED.items():
        if sector_name not in sector_rows:
            sector_rows[sector_name] = Sector(name=sector_name)
            db.add(sector_rows[sector_name])
    db.flush()
    for _t, (_n, _e, _a, sector_name, industry_name, _s) in TIER1_RESOLVED.items():
        key = (sector_name, industry_name)
        if key not in industry_rows:
            industry_rows[key] = Industry(sector_id=sector_rows[sector_name].id, name=industry_name)
            db.add(industry_rows[key])
    db.flush()

    instruments: dict[str, Instrument] = {}
    for ticker, spec in TIER1_RESOLVED.items():
        name, exchange, asset_type, sector_name, industry_name, _s = spec
        inst = Instrument(
            ticker=ticker,
            name=name,
            exchange=exchange,
            asset_type=asset_type,
            industry_id=industry_rows[(sector_name, industry_name)].id,
            active=True,
        )
        db.add(inst)
        instruments[ticker] = inst
    db.flush()

    for ticker in TIER1_RESOLVED:
        db.add(
            InstrumentValidationEvent(
                raw_input=ticker,
                status=InstrumentValidationStatus.RESOLVED,
                canonical_instrument_id=instruments[ticker].id,
                reason="Resolved against Alpaca asset reference: active, tradable.",
                source="alpaca_assets",
                checked_at=NOW,
            )
        )
    for ticker, reason in TIER1_QUARANTINED.items():
        db.add(
            InstrumentValidationEvent(
                raw_input=ticker,
                status=InstrumentValidationStatus.QUARANTINED,
                canonical_instrument_id=None,
                reason=reason,
                source="alpaca_assets",
                checked_at=NOW,
            )
        )
    db.flush()

    watchlist = Watchlist(
        owner_user_id=user.id,
        name="Tier 1",
        description="The core 48-symbol swing-trade watchlist.",
    )
    db.add(watchlist)
    db.flush()

    watchlist_items: dict[str, WatchlistItem] = {}
    for priority, ticker in enumerate(TIER1_RESOLVED):
        speculative = TIER1_RESOLVED[ticker][5]
        item = WatchlistItem(
            watchlist_id=watchlist.id,
            instrument_id=instruments[ticker].id,
            tier=1,
            priority=priority,
            active=True,
            notes="Speculative — smaller position-size cap applies." if speculative else None,
            monitoring_frequency=MonitoringFrequency.DAILY,
            added_at=TODAY - timedelta(days=180),
        )
        db.add(item)
        watchlist_items[ticker] = item
    db.flush()

    return sector_rows, instruments, watchlist, watchlist_items


def _seed_market_evidence(
    db: Session, instruments: dict[str, Instrument], sector_rows: dict[str, Sector]
) -> None:
    evidence_tickers = ["AAPL", "TSLA", "AMD", "PLTR", "JPM"]
    base_prices = {
        "AAPL": Decimal("308.91"),
        "TSLA": Decimal("245.10"),
        "AMD": Decimal("172.40"),
        "PLTR": Decimal("41.85"),
        "JPM": Decimal("221.30"),
    }
    for ticker in evidence_tickers:
        price = base_prices[ticker]
        for i in range(30, -1, -1):
            as_of = TODAY - timedelta(days=i)
            if as_of.weekday() >= 5:
                continue
            drift = Decimal(str(1 + (i % 5 - 2) * 0.003))
            close = (price * drift).quantize(Decimal("0.01"))
            db.add(
                MarketBar(
                    instrument_id=instruments[ticker].id,
                    as_of=as_of,
                    timeframe=Timeframe.DAILY,
                    open=close - Decimal("1.20"),
                    high=close + Decimal("2.30"),
                    low=close - Decimal("2.80"),
                    close=close,
                    volume=42_000_000,
                    adjusted=True,
                    source="alpaca",
                    observed_at=datetime.combine(as_of, datetime.min.time(), tzinfo=UTC),
                )
            )
        for name, value in (
            ("SMA_20", price),
            ("RSI_14", Decimal("54.20")),
            ("ATR_14", Decimal("6.10")),
        ):
            db.add(
                TechnicalIndicatorSnapshot(
                    instrument_id=instruments[ticker].id,
                    as_of=TODAY,
                    indicator_name=name,
                    version="v1",
                    value=value,
                )
            )
        sector_name = TIER1_RESOLVED[ticker][3]
        db.add(
            FundamentalsSnapshot(
                instrument_id=instruments[ticker].id,
                as_of=TODAY,
                market_cap=Decimal("500000000000.00"),
                pe_ratio=Decimal("28.5000"),
                sector_id=sector_rows[sector_name].id,
                source="fmp_free_tier",
                observed_at=NOW,
                quality_status=DataQualityStatus.OK,
            )
        )

    db.add(
        EarningsEvent(
            instrument_id=instruments["TSLA"].id,
            fiscal_period="Q3-2026",
            report_date=TODAY + timedelta(days=4),
            report_time="AMC",
            eps_estimate=Decimal("0.85"),
            eps_actual=None,
            source="finnhub_free_tier",
        )
    )

    news = NewsItem(
        canonical_url="https://example-news.test/aapl-pullback-2026-08-03",
        publisher="Example Wire",
        headline="Apple shares pull back from highs amid broader tech softness",
        published_at=NOW - timedelta(hours=6),
        dedup_hash="seed-hash-aapl-2026-08-03",
        license_metadata={"license": "display-only", "vendor": "alpaca-news"},
    )
    db.add(news)
    db.flush()
    db.add(NewsItemInstrument(news_item_id=news.id, instrument_id=instruments["AAPL"].id))

    db.add(
        SentimentSnapshot(
            instrument_id=instruments["AAPL"].id,
            as_of=NOW,
            score=Decimal("0.1200"),
            source="phase2_deferred_placeholder",
            sample_size=None,
        )
    )

    for i in range(20, -1, -1):
        as_of = TODAY - timedelta(days=i)
        if as_of.weekday() >= 5:
            continue
        db.add(
            MacroObservation(
                series_code="VIXY_CLOSE",
                as_of=as_of,
                value=Decimal("14.20") + Decimal(str(i % 3)),
                source="alpaca",
            )
        )
    db.add(
        MarketRegimeSnapshot(
            as_of=TODAY,
            classification=RegimeClassification.CALM,
            vix_proxy_level=Decimal("14.35"),
            vix_percentile=Decimal("0.3200"),
            vix_rate_of_change=Decimal("-0.0150"),
            breadth_pct_above_sma50=Decimal("0.6200"),
            inputs_snapshot={"vixy_close": "14.35", "breadth_pct_above_sma50": "0.62"},
        )
    )
    db.add(
        DataQualityEvent(
            subject_type="FUNDAMENTALS_SNAPSHOT",
            subject_id=None,
            instrument_id=instruments["SMCI"].id,
            status=DataQualityStatus.STALE,
            detail="Fundamentals vendor rate-limited this cycle; last snapshot is 9 days old.",
            detected_at=NOW,
        )
    )
    db.flush()


def _seed_committee_and_recommendations(
    db: Session, instruments: dict[str, Instrument], watchlist_items: dict[str, WatchlistItem]
) -> tuple[RecommendationVersion, Recommendation, Recommendation]:
    agent_defs: dict[AgentRole, AgentDefinition] = {}
    for role, name in AGENT_ROLE_NAMES.items():
        d = AgentDefinition(role=role, name=name)
        db.add(d)
        agent_defs[role] = d
    db.flush()

    prompt_versions: dict[AgentRole, PromptVersion] = {}
    for role in AGENT_ROLE_NAMES:
        template = PromptTemplate(agent_role=role, name=f"{AGENT_ROLE_NAMES[role]} system prompt")
        db.add(template)
        db.flush()
        pv = PromptVersion(
            prompt_template_id=template.id,
            version_label=f"committee-{role.value.lower()}-v1",
            body=f"You are the {AGENT_ROLE_NAMES[role]} on an investment committee (seed).",
            status=PromptTemplateStatus.ACTIVE,
        )
        db.add(pv)
        prompt_versions[role] = pv
    db.flush()

    agent_versions: dict[AgentRole, AgentVersion] = {}
    for role in AGENT_ROLE_NAMES:
        av = AgentVersion(
            agent_definition_id=agent_defs[role].id,
            version_label=f"committee-{role.value.lower()}-v1",
            prompt_version_id=prompt_versions[role].id,
            model_name="claude-sonnet-5",
            is_active=True,
        )
        db.add(av)
        agent_versions[role] = av
    db.flush()

    session_ = CommitteeSession(
        instrument_id=instruments["AAPL"].id,
        triggered_by="SEED_FIXTURE",
        status=CommitteeSessionStatus.COMPLETED,
        started_at=NOW - timedelta(minutes=3),
        completed_at=NOW,
    )
    db.add(session_)
    db.flush()

    stances: dict[AgentRole, str | None] = {
        AgentRole.BULL: "BULLISH",
        AgentRole.BEAR: "BEARISH",
        AgentRole.TECHNICAL: "NEUTRAL",
        AgentRole.FUNDAMENTAL: "BULLISH",
        AgentRole.MACRO: "NEUTRAL",
        AgentRole.RISK_MANAGER: None,
        AgentRole.PORTFOLIO_MANAGER: None,
        AgentRole.CIO: None,
    }
    for role in AGENT_ROLE_NAMES:
        run = AgentRun(
            committee_session_id=session_.id,
            agent_version_id=agent_versions[role].id,
            status=AgentRunStatus.SUCCEEDED,
            input_snapshot={"instrument": "AAPL", "as_of": str(TODAY)},
            output_snapshot={
                "narrative": f"Seed placeholder narrative for {AGENT_ROLE_NAMES[role]}."
            },
            started_at=NOW - timedelta(minutes=2),
            completed_at=NOW - timedelta(minutes=1),
        )
        db.add(run)
        db.flush()
        db.add(
            AgentEvidenceLink(
                agent_run_id=run.id,
                evidence_type="TECHNICAL_INDICATOR_SNAPSHOT",
                evidence_id=instruments["AAPL"].id,
            )
        )
        db.add(
            AgentOpinion(
                agent_run_id=run.id,
                stance=stances[role],
                structured_output={
                    "summary": f"Seed placeholder opinion for {AGENT_ROLE_NAMES[role]}."
                },
            )
        )
        db.add(
            ModelCallRecord(
                agent_run_id=run.id,
                prompt_version_label=prompt_versions[role].version_label,
                model="claude-sonnet-5",
                input_tokens=1800,
                output_tokens=350,
                cost_usd=Decimal("0.007300"),
                latency_ms=2100,
                stop_reason="end_turn",
                response_excerpt="Seed placeholder response excerpt (truncated).",
            )
        )
    db.flush()

    recommendation = Recommendation(
        instrument_id=instruments["AAPL"].id,
        watchlist_item_id=watchlist_items["AAPL"].id,
        opened_at=NOW,
        status=RecommendationStatus.ACTIVE,
    )
    db.add(recommendation)
    db.flush()
    rec_version = RecommendationVersion(
        recommendation_id=recommendation.id,
        committee_session_id=session_.id,
        version_number=1,
        action=RecommendationAction.BUY,
        confidence=RecommendationConfidence.MEDIUM,
        score=Decimal("62.50"),
        rationale=(
            "AAPL is testing its 50-day SMA with softening short-term momentum; the committee "
            "leans constructive on valuation and fundamentals but flags mixed technical "
            "signals — seed placeholder rationale for demonstration."
        ),
        deterministic_inputs_snapshot={"sma_20": "308.91", "rsi_14": "54.20", "atr_14": "6.10"},
        generated_at=NOW,
    )
    db.add(rec_version)
    db.flush()
    db.add(
        RecommendationLevel(
            recommendation_version_id=rec_version.id,
            kind=RecommendationLevelKind.ENTRY,
            price=Decimal("309.00"),
            basis="Current close",
        )
    )
    db.add(
        RecommendationLevel(
            recommendation_version_id=rec_version.id,
            kind=RecommendationLevelKind.STOP,
            price=Decimal("299.65"),
            basis="1.5x ATR_14 below entry",
        )
    )
    db.add(
        RecommendationLevel(
            recommendation_version_id=rec_version.id,
            kind=RecommendationLevelKind.TARGET,
            price=Decimal("324.40"),
            basis="Prior swing high",
        )
    )
    db.add(
        RecommendationStatusEvent(
            recommendation_id=recommendation.id,
            from_status=None,
            to_status=RecommendationStatus.ACTIVE,
            reason="Initial generation.",
            occurred_at=NOW,
        )
    )

    recommendation_pltr = Recommendation(
        instrument_id=instruments["PLTR"].id,
        watchlist_item_id=watchlist_items["PLTR"].id,
        opened_at=NOW - timedelta(days=3),
        status=RecommendationStatus.ACTIVE,
    )
    db.add(recommendation_pltr)
    db.flush()
    db.add(
        RecommendationVersion(
            recommendation_id=recommendation_pltr.id,
            committee_session_id=None,
            version_number=1,
            action=RecommendationAction.WATCH,
            confidence=RecommendationConfidence.LOW,
            score=Decimal("48.00"),
            rationale="Mixed signals, speculative name — watch for a clearer setup (seed).",
            deterministic_inputs_snapshot={"sma_20": "41.85"},
            generated_at=NOW - timedelta(days=3),
        )
    )
    db.add(
        ConfidenceCalibrationRecord(
            confidence_band=RecommendationConfidence.MEDIUM,
            period_start=TODAY - timedelta(days=90),
            period_end=TODAY,
            sample_size=0,
            hit_rate=None,
            computed_at=NOW,
        )
    )
    db.flush()
    return rec_version, recommendation, recommendation_pltr


def _seed_portfolio(
    db: Session,
    user: UserProfile,
    instruments: dict[str, Instrument],
    rec_version: RecommendationVersion,
) -> tuple[Account, Trade]:
    manual_account = Account(
        owner_user_id=user.id,
        account_type=AccountType.MANUAL,
        name="Personal Journal",
        starting_cash=Decimal("10000.000000"),
    )
    paper_account = Account(
        owner_user_id=user.id,
        account_type=AccountType.PAPER_ALPACA,
        name="Alpaca Paper Sandbox",
        starting_cash=Decimal("10000.000000"),
        broker_account_ref="seed-paper-account-ref",
    )
    db.add_all([manual_account, paper_account])
    db.flush()

    for account in (manual_account, paper_account):
        db.add(
            CashLedgerEntry(
                account_id=account.id,
                entry_type=CashLedgerEntryType.DEPOSIT,
                amount=Decimal("10000.000000"),
                occurred_at=NOW - timedelta(days=200),
                idempotency_key=f"seed-initial-deposit-{account.id}",
            )
        )

    aapl_order = Order(
        account_id=manual_account.id,
        instrument_id=instruments["AAPL"].id,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        quantity=Decimal("10"),
        status=OrderStatus.FILLED,
        submitted_at=NOW - timedelta(days=2),
        filled_at=NOW - timedelta(days=2),
        linked_recommendation_version_id=rec_version.id,
    )
    db.add(aapl_order)
    db.flush()
    db.add(OrderLeg(order_id=aapl_order.id, role=OrderLegRole.PRIMARY))
    aapl_exec = Execution(
        order_id=aapl_order.id,
        quantity=Decimal("10"),
        price=Decimal("306.20"),
        executed_at=NOW - timedelta(days=2),
    )
    db.add(aapl_exec)
    db.flush()
    db.add(Fee(execution_id=aapl_exec.id, fee_type=FeeType.COMMISSION, amount=Decimal("0.000000")))
    db.add(
        CashLedgerEntry(
            account_id=manual_account.id,
            entry_type=CashLedgerEntryType.TRADE_DEBIT,
            amount=Decimal("-3062.000000"),
            related_order_id=aapl_order.id,
            related_execution_id=aapl_exec.id,
            occurred_at=NOW - timedelta(days=2),
            idempotency_key=f"seed-exec-{aapl_exec.id}",
        )
    )
    aapl_position = Position(
        account_id=manual_account.id,
        instrument_id=instruments["AAPL"].id,
        quantity=Decimal("10"),
        avg_cost=Decimal("306.20"),
        opened_at=NOW - timedelta(days=2),
    )
    db.add(aapl_position)
    db.flush()
    db.add(
        PositionLot(
            position_id=aapl_position.id,
            account_id=manual_account.id,
            instrument_id=instruments["AAPL"].id,
            opened_execution_id=aapl_exec.id,
            quantity_opened=Decimal("10"),
            quantity_remaining=Decimal("10"),
            cost_basis_price=Decimal("306.20"),
            opened_at=NOW - timedelta(days=2),
        )
    )

    tsla_buy = Order(
        account_id=manual_account.id,
        instrument_id=instruments["TSLA"].id,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("5"),
        status=OrderStatus.FILLED,
        submitted_at=NOW - timedelta(days=20),
        filled_at=NOW - timedelta(days=20),
    )
    tsla_sell = Order(
        account_id=manual_account.id,
        instrument_id=instruments["TSLA"].id,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("5"),
        status=OrderStatus.FILLED,
        submitted_at=NOW - timedelta(days=8),
        filled_at=NOW - timedelta(days=8),
    )
    db.add_all([tsla_buy, tsla_sell])
    db.flush()
    db.add(OrderLeg(order_id=tsla_buy.id, role=OrderLegRole.PRIMARY))
    db.add(OrderLeg(order_id=tsla_sell.id, role=OrderLegRole.PRIMARY))
    db.add(
        Execution(
            order_id=tsla_buy.id,
            quantity=Decimal("5"),
            price=Decimal("220.00"),
            executed_at=NOW - timedelta(days=20),
        )
    )
    db.add(
        Execution(
            order_id=tsla_sell.id,
            quantity=Decimal("5"),
            price=Decimal("245.10"),
            executed_at=NOW - timedelta(days=8),
        )
    )
    db.flush()
    tsla_trade = Trade(
        account_id=manual_account.id,
        instrument_id=instruments["TSLA"].id,
        status=TradeStatus.CLOSED,
        opened_at=NOW - timedelta(days=20),
        closed_at=NOW - timedelta(days=8),
        quantity=Decimal("5"),
        realized_pnl=Decimal("125.500000"),
    )
    db.add(tsla_trade)
    db.flush()
    db.add(
        TradeThesis(
            trade_id=tsla_trade.id,
            thesis_text="Momentum continuation after a base breakout (seed placeholder).",
            catalyst_text="Delivery-number beat.",
            original_stop_price=Decimal("205.00"),
            is_intact=False,
        )
    )
    db.add(
        TradeNote(
            trade_id=tsla_trade.id,
            note_text="Took profit into strength ahead of the next earnings window.",
        )
    )
    db.add(
        TradeReview(
            trade_id=tsla_trade.id,
            rating=TradeReviewRating.GOOD_PROCESS,
            review_text="Followed the plan; exited on schedule.",
            reviewed_at=NOW - timedelta(days=8),
        )
    )
    db.add(
        PortfolioSnapshot(
            account_id=manual_account.id,
            as_of=NOW,
            cash=Decimal("7063.500000"),
            market_value=Decimal("3089.100000"),
            total_equity=Decimal("10152.600000"),
        )
    )
    db.add(
        RiskSnapshot(
            account_id=manual_account.id,
            as_of=NOW,
            gross_exposure_pct=Decimal("0.3040"),
            largest_position_pct=Decimal("0.3040"),
            sector_concentration={"Technology": "0.3040"},
            correlation_flag=False,
        )
    )
    return manual_account, tsla_trade


def _seed_outcomes(
    db: Session, recommendation: Recommendation, recommendation_pltr: Recommendation
) -> None:
    db.add(
        RecommendationOutcome(
            recommendation_id=recommendation.id,
            classification=RecommendationOutcomeClassification.FOLLOWED,
            linked_trade_id=None,
            matched_at=NOW - timedelta(days=2),
            realized_pnl=None,
            r_multiple=None,
            computed_at=NOW,
        )
    )
    db.add(
        HypotheticalTradeOutcome(
            recommendation_id=recommendation_pltr.id,
            simulated_entry_price=Decimal("41.85"),
            simulated_exit_price=Decimal("40.20"),
            simulated_exit_reason="SIGNAL_EXIT",
            simulated_pnl_pct=Decimal("-3.9400"),
            computed_at=NOW,
        )
    )


def _seed_learning(db: Session, user: UserProfile, instruments: dict[str, Instrument]) -> None:
    strategy_def = StrategyDefinition(
        owner_user_id=user.id,
        name="Default Scoring Strategy",
        description="The active deterministic scoring configuration.",
    )
    db.add(strategy_def)
    db.flush()
    active_strategy = StrategyVersion(
        strategy_definition_id=strategy_def.id,
        config={
            "weights": {"trend": 1.0, "momentum": 1.0, "macd": 1.0, "bollinger": 1.0},
            "rsi_bullish_low": 50,
            "rsi_bullish_high": 70,
            "rsi_oversold": 30,
        },
        status=StrategyVersionStatus.ACTIVE,
        decided_at=NOW - timedelta(days=180),
        decision_comment="Initial version, activated without a prior comparison.",
    )
    db.add(active_strategy)
    db.flush()
    for signal, weight in (
        ("trend", "1.0000"),
        ("momentum", "1.0000"),
        ("macd", "1.0000"),
        ("bollinger", "1.0000"),
    ):
        db.add(
            ScoringWeightVersion(
                strategy_version_id=active_strategy.id, signal_name=signal, weight=Decimal(weight)
            )
        )

    backtest_run = BacktestRun(
        strategy_version_id=active_strategy.id,
        date_range_start=TODAY - timedelta(days=730),
        date_range_end=TODAY,
        parameters={
            "entry_score_threshold": "65",
            "exit_score_threshold": "40",
            "max_holding_days": 10,
            "position_size_pct": "0.10",
            "starting_cash": "10000.00",
            "benchmark_ticker": "SPY",
        },
        results_summary={
            "ending_equity": "11502.809000",
            "total_return_pct": "15.0280900",
            "max_drawdown_pct": "13.649076",
            "win_rate_pct": "42.148760",
            "num_trades": 3,
            "avg_win_pct": "4.686472",
            "avg_loss_pct": "-2.988473",
            "benchmark_return_pct": "44.387104",
            "equity_curve": [],
            "trades": [],
        },
    )
    db.add(backtest_run)
    db.flush()
    db.add(
        BacktestTrade(
            backtest_run_id=backtest_run.id,
            instrument_id=instruments["AAPL"].id,
            entry_date=TODAY - timedelta(days=400),
            entry_price=Decimal("280.00"),
            exit_date=TODAY - timedelta(days=390),
            exit_price=Decimal("291.00"),
            quantity=Decimal("10"),
            pnl_usd=Decimal("110.00"),
            pnl_pct=Decimal("3.9300"),
            exit_reason=BacktestTradeExitReason.SIGNAL_EXIT,
        )
    )
    db.add(
        BacktestTrade(
            backtest_run_id=backtest_run.id,
            instrument_id=instruments["TSLA"].id,
            entry_date=TODAY - timedelta(days=200),
            entry_price=Decimal("210.00"),
            exit_date=TODAY - timedelta(days=190),
            exit_price=Decimal("198.00"),
            quantity=Decimal("5"),
            pnl_usd=Decimal("-60.00"),
            pnl_pct=Decimal("-5.7100"),
            exit_reason=BacktestTradeExitReason.MAX_HOLDING_DAYS,
        )
    )

    proposal = ModelChangeProposal(
        owner_user_id=user.id,
        subject_type="STRATEGY_VERSION",
        subject_ref_id=active_strategy.id,
        description="No change proposed yet — seed placeholder showing the governance shape.",
        status=ModelChangeProposalStatus.APPROVED,
        proposed_at=NOW - timedelta(days=180),
    )
    db.add(proposal)
    db.flush()
    db.add(
        ModelChangeApproval(
            proposal_id=proposal.id,
            decision=ModelChangeProposalStatus.APPROVED,
            comment="Initial version, no comparison needed.",
            decided_at=NOW - timedelta(days=180),
        )
    )


def _seed_performance(db: Session, manual_account: Account) -> None:
    db.add(
        PerformanceSnapshot(
            account_id=manual_account.id,
            period_start=TODAY - timedelta(days=30),
            period_end=TODAY,
            realized_pnl=Decimal("125.500000"),
            win_rate=Decimal("1.0000"),
            avg_r_multiple=Decimal("1.2500"),
            max_drawdown_pct=Decimal("0.0210"),
        )
    )
    db.add(
        BenchmarkSnapshot(
            benchmark_ticker="SPY",
            period_start=TODAY - timedelta(days=30),
            period_end=TODAY,
            return_pct=Decimal("2.1000"),
        )
    )


def _seed_operations(db: Session, user: UserProfile, instruments: dict[str, Instrument]) -> None:
    alert = Alert(
        owner_user_id=user.id,
        instrument_id=instruments["TSLA"].id,
        severity=AlertSeverity.WARNING,
        status=AlertStatus.OPEN,
        title="TSLA earnings inside the swing window",
        detail="Earnings report expected in 4 days — event-risk warning per FR-24.",
        triggered_at=NOW,
    )
    db.add(alert)
    db.flush()
    db.add(
        AlertDelivery(
            alert_id=alert.id,
            channel=NotificationChannel.IN_APP,
            status=AlertDeliveryStatus.DELIVERED,
            delivered_at=NOW,
        )
    )
    db.add(
        JobRun(
            job_name="premarket_plan",
            status=JobRunStatus.SUCCEEDED,
            started_at=NOW - timedelta(hours=7),
            completed_at=NOW - timedelta(hours=7) + timedelta(minutes=4),
            idempotency_key=f"premarket:{TODAY.isoformat()}",
        )
    )


def _seed_r3(
    db: Session,
    user: UserProfile,
    instruments: dict[str, Instrument],
    watchlist_items: dict[str, WatchlistItem],
    recommendation: Recommendation,
    rec_version: RecommendationVersion,
    manual_account: Account,
) -> None:
    """Revision Prompt R3: one representative, synthetic example of every
    new bounded context (decision taxonomy, investment thesis, earnings
    evidence, morning plan, order authority, strategy governance), so
    every new `/api/v1/*` endpoint has real data — no live provider call,
    no plan-generation or trading logic, matching the rest of this
    script's scope."""
    # --- Decision taxonomy: tag the existing AAPL tactical version, add
    # an investment-lane recommendation for AMD ---
    rec_version.lane_action = TacticalAction.TRADE_ENTER.value
    rec_version.horizon_days_min = 1
    rec_version.horizon_days_max = 10
    rec_version.review_date = TODAY + timedelta(days=5)
    db.add(
        RecommendationInvalidationCondition(
            recommendation_version_id=rec_version.id,
            condition_text="Close below the 50-day SMA on above-average volume.",
        )
    )
    aapl_lot = db.scalar(
        select(PositionLot).where(
            PositionLot.account_id == manual_account.id,
            PositionLot.instrument_id == instruments["AAPL"].id,
        )
    )
    if aapl_lot is not None:
        db.add(
            RecommendationAttribution(
                recommendation_version_id=rec_version.id,
                mode=RecommendationMode.TACTICAL,
                position_lot_id=aapl_lot.id,
            )
        )

    amd_recommendation = Recommendation(
        instrument_id=instruments["AMD"].id,
        watchlist_item_id=watchlist_items["AMD"].id,
        mode=RecommendationMode.INVESTMENT,
        opened_at=NOW - timedelta(days=30),
        status=RecommendationStatus.ACTIVE,
    )
    db.add(amd_recommendation)
    db.flush()
    amd_rec_version = RecommendationVersion(
        recommendation_id=amd_recommendation.id,
        version_number=1,
        action=RecommendationAction.BUY,
        lane_action=InvestmentAction.INVEST_BUY.value,
        confidence=RecommendationConfidence.HIGH,
        score=Decimal("74.00"),
        rationale=(
            "AMD's data-center GPU roadmap and margin trajectory support a multi-quarter "
            "accumulation thesis independent of near-term price action (seed placeholder)."
        ),
        deterministic_inputs_snapshot={"sma_20": "172.40"},
        generated_at=NOW - timedelta(days=30),
        horizon_days_min=180,
        horizon_days_max=730,
        review_date=TODAY + timedelta(days=90),
    )
    db.add(amd_rec_version)
    db.flush()

    # --- Investment thesis ---
    thesis = InvestmentThesis(
        recommendation_id=amd_recommendation.id,
        owner_user_id=user.id,
        instrument_id=instruments["AMD"].id,
        status=ThesisStatus.ACTIVE,
    )
    db.add(thesis)
    db.flush()
    thesis_version = InvestmentThesisVersion(
        investment_thesis_id=thesis.id,
        version_number=1,
        valuation_low=Decimal("150.000000"),
        valuation_mid=Decimal("190.000000"),
        valuation_high=Decimal("230.000000"),
        thesis_text=(
            "Data-center GPU attach and gross-margin expansion drive multi-year earnings "
            "growth ahead of consensus (seed placeholder thesis)."
        ),
        horizon_days_min=180,
        horizon_days_max=730,
        review_date=TODAY + timedelta(days=90),
        generated_at=NOW - timedelta(days=30),
    )
    db.add(thesis_version)
    db.flush()
    db.add(
        ThesisCatalyst(
            investment_thesis_version_id=thesis_version.id,
            catalyst_text="Next-generation accelerator launch.",
            expected_date=TODAY + timedelta(days=120),
        )
    )
    db.add(
        ThesisRisk(
            investment_thesis_version_id=thesis_version.id,
            risk_text="Customer concentration among a small number of hyperscalers.",
        )
    )
    db.add(
        ValuationSnapshot(
            investment_thesis_id=thesis.id,
            as_of=TODAY - timedelta(days=1),
            method="DCF",
            fair_value_low=Decimal("150.000000"),
            fair_value_mid=Decimal("190.000000"),
            fair_value_high=Decimal("230.000000"),
            source="internal_model",
            observed_at=NOW - timedelta(days=1),
        )
    )
    db.add(
        ThesisStatusHistory(
            investment_thesis_id=thesis.id,
            from_status=None,
            to_status=ThesisStatus.ACTIVE,
            reason="Initial thesis generation.",
            occurred_at=NOW - timedelta(days=30),
        )
    )

    # --- Earnings evidence: one upcoming (pre-event only) event, one
    # already-reported event (actual + post-event confirmation) ---
    upcoming_earnings = EarningsEvent(
        instrument_id=instruments["AMD"].id,
        fiscal_period="Q3-2026",
        report_date=TODAY + timedelta(days=10),
        report_time="AMC",
        eps_estimate=Decimal("1.15"),
        source="finnhub_free_tier",
        verified_date=TODAY - timedelta(days=1),
        exchange_local_date=TODAY + timedelta(days=10),
        timing_category=EarningsTimingCategory.AFTER_CLOSE,
        verification_source="company_ir_page",
        expected_report_period="Q3-2026",
        confidence=RecommendationConfidence.HIGH,
    )
    db.add(upcoming_earnings)
    db.flush()
    db.add(
        EarningsConsensusSnapshot(
            earnings_event_id=upcoming_earnings.id,
            as_of=TODAY - timedelta(days=1),
            consensus_eps=Decimal("1.1500"),
            consensus_revenue=Decimal("8200000000.00"),
            num_analysts=32,
            source="finnhub_free_tier",
            observed_at=NOW - timedelta(days=1),
        )
    )
    db.add(
        EarningsGuidanceItem(
            earnings_event_id=upcoming_earnings.id,
            metric="revenue",
            guidance_low=Decimal("8000000000.0000"),
            guidance_high=Decimal("8400000000.0000"),
            period="Q3-2026",
            issued_at=NOW - timedelta(days=45),
            source="company_ir_page",
        )
    )
    db.add(
        EventExpectedMoveSnapshot(
            earnings_event_id=upcoming_earnings.id,
            as_of=NOW,
            evidence_cutoff=NOW,
            atr_based_move_pct=Decimal("6.2000"),
            historical_gap_move_pct=Decimal("7.1000"),
            option_implied_move_pct=Decimal("6.8000"),
            selected_expected_move_pct=Decimal("6.8000"),
            calculation_version="v1",
        )
    )
    db.add(
        EarningsFeatureSnapshot(
            earnings_event_id=upcoming_earnings.id,
            as_of=NOW,
            evidence_cutoff=NOW,
            is_pre_event=True,
            component_price_trend=Decimal("0.7200"),
            component_analyst_revisions=Decimal("0.6500"),
            component_options_skew=Decimal("0.5000"),
            component_peer_reactions=Decimal("0.5800"),
            component_historical_drift=Decimal("0.6100"),
            component_guidance_momentum=Decimal("0.7000"),
            component_technical_setup=Decimal("0.5500"),
            component_sentiment=Decimal("0.6000"),
            total_score=Decimal("7.20"),
            calculation_version="v1",
        )
    )

    reported_earnings = EarningsEvent(
        instrument_id=instruments["MRVL"].id,
        fiscal_period="Q2-2026",
        report_date=TODAY - timedelta(days=5),
        report_time="AMC",
        eps_estimate=Decimal("0.65"),
        eps_actual=Decimal("0.71"),
        source="finnhub_free_tier",
        verified_date=TODAY - timedelta(days=6),
        exchange_local_date=TODAY - timedelta(days=5),
        timing_category=EarningsTimingCategory.AFTER_CLOSE,
        verification_source="company_ir_page",
        expected_report_period="Q2-2026",
        confidence=RecommendationConfidence.HIGH,
    )
    db.add(reported_earnings)
    db.flush()
    actual_usable_at = datetime.combine(
        TODAY - timedelta(days=5), datetime.min.time(), tzinfo=UTC
    ) + timedelta(hours=16, minutes=5)
    db.add(
        EarningsActual(
            earnings_event_id=reported_earnings.id,
            metric="eps",
            actual_value=Decimal("0.7100"),
            reported_at=actual_usable_at - timedelta(minutes=5),
            usable_at=actual_usable_at,
            source="company_ir_page",
        )
    )
    db.add(
        PostEarningsConfirmationSnapshot(
            earnings_event_id=reported_earnings.id,
            as_of=NOW - timedelta(days=4),
            evidence_cutoff=actual_usable_at + timedelta(hours=1),
            results_gate_passed=True,
            guidance_gate_passed=True,
            market_reaction_gate_passed=True,
            all_gates_passed=True,
            notes="Beat on EPS with raised forward guidance and a confirmed positive reaction "
            "(seed placeholder).",
        )
    )

    # --- Morning plan ---
    plan_run = MorningPlanRun(
        plan_date=TODAY,
        triggered_by="seed_fixture",
        status=MorningPlanRunStatus.COMPLETED,
        started_at=NOW - timedelta(minutes=10),
        completed_at=NOW - timedelta(minutes=9),
    )
    db.add(plan_run)
    db.flush()
    plan_version = MorningPlanVersion(
        morning_plan_run_id=plan_run.id,
        plan_date=TODAY,
        version_label=MorningPlanVersionLabel.FINAL,
        version_number=1,
        evidence_cutoff=NOW - timedelta(minutes=9),
        generated_at=NOW - timedelta(minutes=9),
        completeness_status=PlanCompletenessStatus.COMPLETE,
    )
    db.add(plan_version)
    db.flush()
    act_now_section = MorningPlanSection(
        morning_plan_version_id=plan_version.id,
        section_key=MorningPlanSectionKey.ACT_NOW,
        display_order=1,
    )
    data_problems_section = MorningPlanSection(
        morning_plan_version_id=plan_version.id,
        section_key=MorningPlanSectionKey.DATA_PROBLEMS,
        display_order=7,
    )
    db.add_all([act_now_section, data_problems_section])
    db.flush()
    db.add(
        MorningPlanItem(
            morning_plan_section_id=act_now_section.id,
            recommendation_version_id=rec_version.id,
            display_order=1,
            headline="AAPL — tactical entry near the 50-day SMA (seed placeholder).",
        )
    )
    db.add(
        MorningPlanItem(
            morning_plan_section_id=data_problems_section.id,
            recommendation_version_id=None,
            display_order=1,
            headline="SMCI fundamentals snapshot is 9 days stale — vendor rate-limited.",
        )
    )
    db.add(
        MorningPlanQualityCheck(
            morning_plan_version_id=plan_version.id,
            check_name="all_watchlist_instruments_have_fresh_bars",
            passed=True,
        )
    )
    db.add(
        MorningPlanQualityCheck(
            morning_plan_version_id=plan_version.id,
            check_name="no_stale_fundamentals_beyond_7_days",
            passed=False,
            detail="SMCI fundamentals snapshot is 9 days old (see Data Problems section).",
        )
    )
    db.add(
        MorningPlanDeliveryEvent(
            morning_plan_version_id=plan_version.id,
            channel=DeliveryChannel.IN_APP,
            status=AlertDeliveryStatus.DELIVERED,
            delivered_at=NOW - timedelta(minutes=8),
        )
    )

    # --- Order authority: one full proposal -> policy evaluation ->
    # pending approval chain, plus mode-history/kill-switch/attestation
    # rows ---
    proposal = OrderProposal(
        recommendation_version_id=rec_version.id,
        account_id=manual_account.id,
        instrument_id=instruments["AAPL"].id,
        mode=RecommendationMode.TACTICAL,
        side=OrderSide.BUY,
        status=OrderProposalStatus.EVALUATED,
    )
    db.add(proposal)
    db.flush()
    proposal_version = OrderProposalVersion(
        order_proposal_id=proposal.id,
        version_number=1,
        order_type=OrderType.MARKET,
        quantity=Decimal("5"),
        time_in_force=TimeInForce.DAY,
        rationale="Seed placeholder proposal from the AAPL tactical recommendation.",
    )
    db.add(proposal_version)
    db.flush()
    db.add(
        OrderPolicyEvaluation(
            order_proposal_version_id=proposal_version.id,
            evaluated_at=NOW - timedelta(minutes=5),
            requested_mode=OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
            authorized=True,
        )
    )

    bound_fields_input = BoundFieldsSnapshot(
        account_id=manual_account.id,
        instrument_id=instruments["AAPL"].id,
        side=OrderSide.BUY.value,
        quantity=Decimal("5"),
        order_type=OrderType.MARKET.value,
        limit_price=None,
        stop_price=None,
        time_in_force=TimeInForce.DAY.value,
        outside_hours=False,
        attached_legs={},
        max_notional=None,
        recommendation_version_id=rec_version.id,
    )
    approval = OrderApproval(
        order_proposal_version_id=proposal_version.id,
        requested_at=NOW - timedelta(minutes=4),
        expires_at=NOW + timedelta(minutes=1),
        status=OrderApprovalStatus.PENDING,
        integrity_hash=compute_bound_fields_hash(bound_fields_input),
    )
    db.add(approval)
    db.flush()
    db.add(
        ApprovalBoundFields(
            order_approval_id=approval.id,
            account_id=manual_account.id,
            instrument_id=instruments["AAPL"].id,
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            outside_hours=False,
            attached_legs={},
            recommendation_version_id=rec_version.id,
        )
    )
    db.add(
        OperatingModeHistory(
            mode=OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
            changed_by="seed_fixture",
            changed_at=NOW - timedelta(days=1),
            reason="Initial mode selection (seed placeholder).",
        )
    )
    db.add(
        ExecutionKillSwitchEvent(
            activated_by="seed_fixture",
            activated_at=NOW - timedelta(days=30),
            deactivated_at=NOW - timedelta(days=30) + timedelta(minutes=15),
            reason="Manual test activation, immediately deactivated (seed placeholder).",
        )
    )
    db.add(
        BrokerEnvironmentAttestation(
            environment_label=EnvironmentLabel.PAPER,
            account_id=None,
            broker_endpoint="https://paper-api.alpaca.markets",
            attested_by="seed_fixture",
            attested_at=NOW - timedelta(days=1),
        )
    )

    # --- Strategy governance ---
    earnings_strategy_def = StrategyDefinition(
        owner_user_id=user.id,
        name="Earnings Pre-Event Momentum",
        description="Pre-event earnings-direction scoring strategy (seed placeholder).",
        family=StrategyFamily.EARNINGS_PRE_EVENT,
    )
    db.add(earnings_strategy_def)
    db.flush()
    earnings_strategy_version = StrategyVersion(
        strategy_definition_id=earnings_strategy_def.id,
        config={"min_total_score": "6.00"},
        status=StrategyVersionStatus.ACTIVE,
        decided_at=NOW - timedelta(days=30),
        decision_comment="Initial version, activated without a prior comparison.",
    )
    db.add(earnings_strategy_version)
    db.flush()
    db.add(
        StrategyEligibilitySnapshot(
            strategy_version_id=earnings_strategy_version.id,
            instrument_id=instruments["AMD"].id,
            as_of=TODAY,
            eligible=True,
            reason="Upcoming earnings within the 10-14 day pre-event window.",
        )
    )
    db.add(
        DecisionPolicyVersion(
            owner_user_id=user.id,
            version_label="r3-seed-v1",
            config={"lanes_enabled": ["INVESTMENT", "TACTICAL"]},
            status=StrategyVersionStatus.ACTIVE,
            decided_at=NOW - timedelta(days=1),
            decision_comment="Initial decision-policy version (seed placeholder).",
        )
    )
    risk_policy = db.scalar(select(RiskPolicy).where(RiskPolicy.owner_user_id == user.id))
    assert risk_policy is not None
    db.add(
        RiskPolicyVersion(
            risk_policy_id=risk_policy.id,
            risk_budget_pct=risk_policy.risk_budget_pct,
            max_position_pct=risk_policy.max_position_pct,
            max_sector_pct=risk_policy.max_sector_pct,
            max_correlation=risk_policy.max_correlation,
            speculative_position_pct_cap=risk_policy.speculative_position_pct_cap,
            changed_at=NOW - timedelta(days=1),
        )
    )


def _seed(db: Session) -> None:
    if db.query(UserProfile).first() is not None:
        print("Seed data already present (UserProfile exists) — skipping.")
        return

    user = _seed_identity(db)
    sector_rows, instruments, _watchlist, watchlist_items = _seed_security_master(db, user)
    _seed_market_evidence(db, instruments, sector_rows)
    rec_version, recommendation, recommendation_pltr = _seed_committee_and_recommendations(
        db, instruments, watchlist_items
    )
    manual_account, _tsla_trade = _seed_portfolio(db, user, instruments, rec_version)
    _seed_outcomes(db, recommendation, recommendation_pltr)
    _seed_learning(db, user, instruments)
    _seed_performance(db, manual_account)
    _seed_operations(db, user, instruments)
    _seed_r3(db, user, instruments, watchlist_items, recommendation, rec_version, manual_account)

    db.commit()
    print(
        f"Seeded {len(TIER1_RESOLVED)} resolved + {len(TIER1_QUARANTINED)} quarantined "
        "Tier 1 instruments, 2 accounts, 1 committee session (8 agent runs), "
        "2 recommendations, 1 backtest run, operations fixtures, and Revision "
        "Prompt R3's decision taxonomy / investment thesis / earnings evidence / "
        "morning plan / order authority / strategy governance fixtures."
    )


def main() -> None:
    db = SessionLocal()
    try:
        _seed(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
