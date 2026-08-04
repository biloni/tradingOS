# Entity-Relationship Diagrams

A single ~70-entity ER diagram is unreadable, so this document is one
context-map overview (which bounded contexts reference which) followed by
one detailed Mermaid `erDiagram` per bounded context. Every table name
below matches `apps/api/src/tradingos_api/models/*.py` and
`docs/DATA_DICTIONARY.md` exactly. Attributes shown are the ones relevant
to relationships and key business rules — see the data dictionary for the
full column list of every table.

## Context map

```mermaid
graph LR
    Identity["1. Identity & Preferences<br/>user_profile, risk_policy, provider_config"]
    Security["2. Security Master & Watchlists<br/>instruments, watchlists, watchlist_items"]
    Evidence["3. Market Evidence<br/>market_bars, news_items, market_regime_snapshots"]
    Agents["4. Agent & Committee<br/>agent_runs, committee_sessions, agent_opinions"]
    Recs["5. Recommendations<br/>recommendations, recommendation_versions"]
    Exec["6. Portfolio & Execution<br/>accounts, orders, positions, position_lots"]
    Learning["7. Outcomes & Learning<br/>recommendation_outcomes, strategy_versions, backtest_runs"]
    Ops["8. Operations<br/>alerts, job_runs, model_call_records, audit_events"]

    Security -->|instrument_id FK| Evidence
    Security -->|instrument_id FK| Recs
    Security -->|instrument_id FK| Exec
    Security -->|instrument_id FK| Agents
    Security -->|watchlist_item_id FK| Recs
    Identity -->|owner_user_id FK, every OwnedMixin table| Security
    Identity -->|owner_user_id FK| Exec
    Identity -->|owner_user_id FK| Ops
    Identity -->|owner_user_id FK| Learning
    Agents -->|committee_session_id FK| Recs
    Agents -->|agent_run_id FK| Ops
    Recs -->|linked_recommendation_version_id FK| Exec
    Recs -->|recommendation_id FK| Learning
    Exec -->|linked_trade_id / trade_id FK| Learning
    Learning -->|strategy_version_id FK| Learning
    Ops -.->|audit_events: generic ref_id, no FK| Security
    Ops -.->|audit_events: generic ref_id, no FK| Exec
```

The dotted lines from `audit_events` and the generic-link tables
(`agent_evidence_links.evidence_id`, `data_quality_events.subject_id`,
`model_change_proposals.subject_ref_id`) are deliberately **not** real
foreign keys (ADR-015's original reasoning, carried forward) — one log
table spans many different target tables, so a single typed FK column
can't express it. `subject_type`/`evidence_type` is the discriminator.

## 1. Identity & preferences

```mermaid
erDiagram
    user_profile ||--o{ investment_profile : owns
    user_profile ||--o{ risk_policy : owns
    user_profile ||--o{ notification_preferences : owns

    user_profile {
        uuid id PK
        string display_name
        string timezone
    }
    investment_profile {
        uuid id PK
        uuid owner_user_id FK
        numeric starting_capital_usd
        enum risk_tolerance
    }
    risk_policy {
        uuid id PK
        uuid owner_user_id FK
        numeric risk_budget_pct
        numeric max_position_pct
    }
    notification_preferences {
        uuid id PK
        uuid owner_user_id FK
        enum channel
        string category
    }
    provider_config {
        uuid id PK
        enum provider_kind
        string provider_name
        bool is_enabled
    }
```

## 2. Security master & watchlists

```mermaid
erDiagram
    sectors ||--o{ industries : contains
    industries ||--o{ instruments : classifies
    instruments ||--o{ instrument_aliases : "known as"
    instruments ||--o{ instrument_validation_events : "resolved from"
    instruments ||--o{ watchlist_items : "member via"
    user_profile ||--o{ watchlists : owns
    watchlists ||--o{ watchlist_items : contains

    sectors { uuid id PK, string name }
    industries { uuid id PK, uuid sector_id FK, string name }
    instruments {
        uuid id PK
        string ticker UK
        string name
        enum asset_type
        uuid industry_id FK
        bool active
    }
    instrument_aliases { uuid id PK, uuid instrument_id FK, string alias, string alias_type }
    instrument_validation_events {
        uuid id PK
        string raw_input
        enum status
        uuid canonical_instrument_id FK
    }
    watchlists { uuid id PK, uuid owner_user_id FK, string name }
    watchlist_items {
        uuid id PK
        uuid watchlist_id FK
        uuid instrument_id FK
        int tier
        int priority
        bool active
    }
```

## 3. Market evidence

```mermaid
erDiagram
    instruments ||--o{ market_bars : "priced by"
    instruments ||--o{ corporate_actions : "affected by"
    instruments ||--o{ technical_indicator_snapshots : "derived for"
    instruments ||--o{ fundamentals_snapshots : "reported for"
    instruments ||--o{ earnings_events : "reports"
    earnings_events ||--o{ earnings_revisions : revised_by
    instruments ||--o{ sentiment_snapshots : "scored for"
    instruments }o--o{ news_items : "mentions (via news_item_instruments)"

    market_bars { uuid id PK, uuid instrument_id FK, date as_of, enum timeframe, numeric close }
    corporate_actions { uuid id PK, uuid instrument_id FK, enum action_type, date ex_date }
    technical_indicator_snapshots {
        uuid id PK
        uuid instrument_id FK
        date as_of
        string indicator_name
        string version
        numeric value
    }
    fundamentals_snapshots { uuid id PK, uuid instrument_id FK, date as_of, numeric market_cap }
    earnings_events { uuid id PK, uuid instrument_id FK, date report_date, numeric eps_estimate }
    earnings_revisions { uuid id PK, uuid earnings_event_id FK, enum direction }
    news_items { uuid id PK, string canonical_url, string dedup_hash UK }
    news_item_instruments { uuid id PK, uuid news_item_id FK, uuid instrument_id FK }
    sentiment_snapshots { uuid id PK, uuid instrument_id FK, datetime as_of, numeric score }
    macro_observations { uuid id PK, string series_code, date as_of, numeric value }
    market_regime_snapshots { uuid id PK, date as_of UK, enum classification }
    data_quality_events { uuid id PK, string subject_type, uuid subject_id, uuid instrument_id FK }
```

## 4. Agent & committee orchestration

```mermaid
erDiagram
    agent_definitions ||--o{ agent_versions : versioned_by
    prompt_versions ||--o{ agent_versions : configures
    instruments ||--o{ committee_sessions : evaluated_in
    committee_sessions ||--o{ agent_runs : contains
    agent_versions ||--o{ agent_runs : executes_as
    agent_runs ||--o| agent_opinions : produces
    agent_runs ||--o{ agent_evidence_links : cites
    agent_runs ||--o{ model_call_records : "underlies (§8)"

    agent_definitions { uuid id PK, enum role UK, string name }
    agent_versions {
        uuid id PK
        uuid agent_definition_id FK
        string version_label
        uuid prompt_version_id FK
        string model_name
    }
    committee_sessions { uuid id PK, uuid instrument_id FK, enum status }
    agent_runs {
        uuid id PK
        uuid committee_session_id FK
        uuid agent_version_id FK
        enum status
        json input_snapshot
        json output_snapshot
    }
    agent_evidence_links { uuid id PK, uuid agent_run_id FK, string evidence_type, uuid evidence_id }
    agent_opinions { uuid id PK, uuid agent_run_id FK UK, string stance, json structured_output }
```

## 5. Recommendations

```mermaid
erDiagram
    instruments ||--o{ recommendations : "our call on"
    watchlist_items ||--o{ recommendations : "sourced from"
    committee_sessions ||--o{ recommendation_versions : "produced by"
    recommendations ||--o{ recommendation_versions : "has history of"
    recommendation_versions ||--o{ recommendation_levels : specifies
    recommendations ||--o{ recommendation_status_events : "transitions logged in"

    recommendations {
        uuid id PK
        uuid instrument_id FK
        uuid watchlist_item_id FK
        enum status
        datetime opened_at
    }
    recommendation_versions {
        uuid id PK
        uuid recommendation_id FK
        uuid committee_session_id FK
        int version_number
        enum action
        enum confidence
        numeric score
    }
    recommendation_levels { uuid id PK, uuid recommendation_version_id FK, enum kind, numeric price }
    recommendation_status_events {
        uuid id PK
        uuid recommendation_id FK
        enum from_status
        enum to_status
    }
    confidence_calibration_records { uuid id PK, enum confidence_band, date period_start }
```

## 6. Portfolio & execution

```mermaid
erDiagram
    user_profile ||--o{ accounts : owns
    accounts ||--o{ cash_ledger : "ledgered by"
    accounts ||--o{ positions : holds
    accounts ||--o{ orders : places
    instruments ||--o{ positions : "held as"
    instruments ||--o{ orders : "targets"
    positions ||--o{ position_lots : "composed of"
    orders ||--o| order_legs : "structured by"
    orders ||--o{ executions : fills
    executions ||--o{ fees : incurs
    executions ||--o{ position_lots : opens
    accounts ||--o{ trades : "round-trips in"
    trades ||--o| trade_theses : justified_by
    trades ||--o{ trade_notes : annotated_by
    trade_notes ||--o{ trade_attachments : attaches
    accounts ||--o{ portfolio_snapshots : "snapshotted as"
    accounts ||--o{ risk_snapshots : "risk-assessed as"

    accounts {
        uuid id PK
        uuid owner_user_id FK
        enum account_type
        numeric starting_cash
    }
    cash_ledger {
        uuid id PK
        uuid account_id FK
        enum entry_type
        numeric amount
        string idempotency_key UK
    }
    positions {
        uuid id PK
        uuid account_id FK
        uuid instrument_id FK
        numeric quantity
        numeric avg_cost
    }
    position_lots {
        uuid id PK
        uuid position_id FK
        uuid opened_execution_id FK
        numeric quantity_opened
        numeric quantity_remaining
        datetime closed_at
    }
    orders {
        uuid id PK
        uuid account_id FK
        uuid instrument_id FK
        enum side
        enum status
        string idempotency_key UK
    }
    order_legs { uuid id PK, uuid order_id FK UK, enum role, uuid bracket_group_id }
    executions { uuid id PK, uuid order_id FK, numeric quantity, numeric price }
    fees { uuid id PK, uuid execution_id FK, enum fee_type, numeric amount }
    trades { uuid id PK, uuid account_id FK, uuid instrument_id FK, enum status, numeric realized_pnl }
    trade_theses { uuid id PK, uuid trade_id FK, bool is_intact }
    trade_notes { uuid id PK, uuid trade_id FK, text note_text }
    trade_attachments { uuid id PK, uuid trade_note_id FK, string file_name }
    portfolio_snapshots { uuid id PK, uuid account_id FK, date as_of UK, numeric total_equity }
    risk_snapshots { uuid id PK, uuid account_id FK, datetime as_of, numeric gross_exposure_pct }
```

## 7. Outcomes & learning

```mermaid
erDiagram
    recommendations ||--o| recommendation_outcomes : "resolved into"
    trades ||--o| recommendation_outcomes : "matched to"
    recommendations ||--o{ hypothetical_trade_outcomes : "simulated for"
    trades ||--o{ trade_reviews : reviewed_by
    accounts ||--o{ performance_snapshots : "measured by"
    user_profile ||--o{ strategy_definitions : owns
    strategy_definitions ||--o{ strategy_versions : versioned_by
    strategy_versions ||--o{ scoring_weight_versions : "projects weights into"
    strategy_versions ||--o{ backtest_runs : "backtested as"
    user_profile ||--o{ model_change_proposals : proposes
    model_change_proposals ||--o{ model_change_approvals : "decided via"

    recommendation_outcomes {
        uuid id PK
        uuid recommendation_id FK UK
        enum classification
        uuid linked_trade_id FK
        numeric r_multiple
    }
    hypothetical_trade_outcomes { uuid id PK, uuid recommendation_id FK, numeric simulated_pnl_pct }
    trade_reviews { uuid id PK, uuid trade_id FK, enum rating }
    performance_snapshots { uuid id PK, uuid account_id FK, date period_start, numeric realized_pnl }
    benchmark_snapshots { uuid id PK, string benchmark_ticker, date period_start }
    strategy_definitions { uuid id PK, uuid owner_user_id FK, string name }
    strategy_versions {
        uuid id PK
        uuid strategy_definition_id FK
        json config
        enum status
    }
    scoring_weight_versions { uuid id PK, uuid strategy_version_id FK, string signal_name, numeric weight }
    model_change_proposals { uuid id PK, uuid owner_user_id FK, string subject_type, enum status }
    model_change_approvals { uuid id PK, uuid proposal_id FK, enum decision }
```

## 8. Backtesting

```mermaid
erDiagram
    strategy_versions ||--o{ backtest_runs : replays
    backtest_runs ||--o{ backtest_trades : "normalized into"
    instruments ||--o{ backtest_trades : "traded in"

    backtest_runs {
        uuid id PK
        uuid strategy_version_id FK
        date date_range_start
        json results_summary
    }
    backtest_trades {
        uuid id PK
        uuid backtest_run_id FK
        uuid instrument_id FK
        numeric pnl_usd
        enum exit_reason
    }
```

## 9. Operations

```mermaid
erDiagram
    user_profile ||--o{ alerts : owns
    instruments ||--o{ alerts : concerns
    alerts ||--o{ alert_deliveries : "delivered via"
    prompt_templates ||--o{ prompt_versions : versioned_by
    agent_runs ||--o{ model_call_records : "billed to (nullable — §4)"

    alerts {
        uuid id PK
        uuid owner_user_id FK
        uuid instrument_id FK
        enum severity
        enum status
    }
    alert_deliveries { uuid id PK, uuid alert_id FK, enum channel, enum status }
    job_runs { uuid id PK, string job_name, enum status, string idempotency_key UK }
    prompt_templates { uuid id PK, enum agent_role, string name }
    prompt_versions { uuid id PK, uuid prompt_template_id FK, string version_label, text body }
    model_call_records {
        uuid id PK
        uuid agent_run_id FK
        string model
        int input_tokens
        numeric cost_usd
    }
    audit_events { uuid id PK, string record_type, uuid ref_id, json snapshot }
```
