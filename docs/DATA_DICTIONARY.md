# Data Dictionary

**Phase 8 (current)** replaced the shipped MVP's 9-table schema wholesale
with a ~70-entity domain model spanning 13 bounded contexts (ADR-043) — see
"Historical: Phase 1-7 schema" at the bottom of this document for what
existed before and exactly what was retired. Three table names survive the
rewrite with reshaped columns (`recommendations`, `backtest_runs`,
`audit_events`); everything else is new. Every table uses a UUID primary
key (`sa.Uuid(as_uuid=True)`, `UUIDPkMixin`) and UTC timestamps
(`sa.DateTime(timezone=True)`).

## Shared column mixins (`db/mixins.py`)

- **`UUIDPkMixin`** — `id: UUID`, server-generated.
- **`CreatedAtMixin`** — `created_at`, set once, never updated.
- **`TimestampMixin`** — adds `updated_at` (`onupdate=sa.func.now()`) — used
  by every mutable-in-place table, and is the field optimistic-concurrency
  PATCH endpoints compare against (`expected_updated_at`).
- **`OwnedMixin`** — adds `owner_user_id` (FK to `user_profile`, NOT NULL).
  Present even though this is a single-user system today ("add row
  ownership even though the initial system is single-user") — every
  `Account`, `Watchlist`, `Alert`, etc. row already carries a real owner so
  a future multi-user phase adds a `WHERE owner_user_id = :me` clause, not
  a migration.

## Enum strategy (`models/enums.py`)

Unlike the shipped MVP's SQLite-era work-arounds, this schema runs on real
Postgres — every enum below (36 total) is a **native Postgres `ENUM` type**
(`sa.Enum(PythonEnum, name=...)`), not a `String` column with app-level
validation. Lifecycle-bearing enums (`OrderStatus`, `RecommendationStatus`,
`AlertStatus`, `BpStatus`-equivalent flows, etc.) each have a co-located
`*_TRANSITIONS: dict[str, set[str]]` map and are enforced through the one
shared `services/lifecycle.py::assert_transition_allowed()` helper — no
router ever hand-rolls a status check.

## 1. Identity & preferences (`models/identity.py`)

| Table | Key fields | Notes |
|---|---|---|
| `user_profile` | `display_name`, `timezone` | The one user (ADR-007, single-user). Lazily created by the seed script; every `OwnedMixin` FK points here. |
| `investment_profile` | `owner_user_id`, `starting_capital_usd`, `risk_tolerance` (enum), `holding_period_min_days`/`max_days` | *Who the user is* — persona-level facts, distinct from `risk_policy`. |
| `risk_policy` | `owner_user_id`, `risk_budget_pct`, `max_position_pct`, `max_sector_pct`, `max_correlation`, `speculative_position_pct_cap` (all `Numeric(6,4)`) | *The numeric limits currently in force* — a single settings row mutated in place (`TimestampMixin`), not versioned/approved like a `StrategyVersion`. `PATCH /api/v1/settings/risk-policy` is the one write path. |
| `notification_preferences` | `owner_user_id`, `channel` (enum), `category`, `enabled` | Unique on `(owner_user_id, channel, category)`. |
| `provider_config` | `provider_kind` (enum: `MARKET_DATA\|BROKER\|LLM\|NEWS\|FUNDAMENTALS`), `provider_name`, `is_enabled`, `config_metadata` (JSON) | **No secret value is ever a column here** — API keys live only in `.env`. `GET /api/v1/settings/providers` cross-references `config_metadata` against which env vars are actually set to report `has_credential_configured`, never the value itself. |

## 2. Security master & watchlists (`models/security_master.py`)

| Table | Key fields | Notes |
|---|---|---|
| `sectors` | `name` (unique) | |
| `industries` | `sector_id` FK, `name` | |
| `instruments` | `ticker` (unique, indexed), `name`, `exchange`, `asset_type` (enum), `industry_id` FK (nullable), `active` | Supersedes the MVP's `Symbol`. Master data — never carries transactional history. A raw ticker that doesn't resolve never becomes a row here (see `instrument_validation_events`). |
| `instrument_aliases` | `instrument_id` FK, `alias`, `alias_type` | Unique on `(alias, alias_type)`. Lets a renamed/legacy ticker still resolve to the current canonical instrument. |
| `instrument_validation_events` | `raw_input` (indexed), `status` (enum: `RESOLVED\|AMBIGUOUS\|QUARANTINED`), `canonical_instrument_id` FK (nullable), `reason`, `source`, `checked_at` | Append-only. A `QUARANTINED` row has `canonical_instrument_id = NULL` and a human-readable `reason` — `raw_input` is preserved verbatim regardless of outcome. |
| `watchlists` | `owner_user_id`, `name`, `description` | |
| `watchlist_items` | `watchlist_id` FK, `instrument_id` FK, `tier` (int), `priority` (int), `active`, `notes`, `monitoring_frequency` (enum), `added_at` (date) | Unique on `(watchlist_id, instrument_id)` — enforced both by the DB constraint and a `409` in `routers/watchlists.py`. A `QUARANTINED` instrument can still be a member row (visible as "wanted but not usable"). |

## 3. Market evidence (`models/market_evidence.py`)

Every table here carries **source + as-of/observed time + ingestion time**
(+ `quality_status` where a value can legitimately be uncertain) — the
provenance envelope the brief requires, applied uniformly across all
evidence types, not just prices.

| Table | Key fields | Notes |
|---|---|---|
| `market_bars` | `instrument_id`, `as_of`, `timeframe` (enum), OHLCV (`Numeric(18,6)`/`BigInteger`), `adjusted`, `source`, `observed_at`, `ingested_at` | Append-only, **no** unique constraint on `(instrument_id, as_of, timeframe)` — a corrective re-fetch is a new row, ordered by `ingested_at` for "latest". Indexed on `(instrument_id, as_of, timeframe)`. |
| `corporate_actions` | `instrument_id`, `action_type` (enum), `ex_date`, `ratio`/`amount` (nullable), `source` | Splits, dividends, etc. |
| `technical_indicator_snapshots` | `instrument_id`, `as_of`, `indicator_name`, `version`, `value` | Unique on `(instrument_id, as_of, indicator_name, version)` — idempotent by formula version, since it's a pure function of `market_bars`. |
| `fundamentals_snapshots` | `instrument_id`, `as_of`, `market_cap`, `pe_ratio`, `sector_id`, `source`, `observed_at`/`ingested_at`, `quality_status` (enum) | |
| `earnings_events` | `instrument_id`, `fiscal_period`, `report_date`, `report_time`, `eps_estimate`/`eps_actual` | |
| `earnings_revisions` | `earnings_event_id` FK, `revised_at`, `previous_eps_estimate`, `new_eps_estimate`, `direction` (enum) | |
| `news_items` | `canonical_url` (indexed), `publisher`, `headline`, `published_at`, `ingested_at`, `dedup_hash` (unique, indexed), `license_metadata` (JSON) | `dedup_hash` is the idempotency key for provider ingestion. `license_metadata` records what the licensing vendor's terms permit. |
| `news_item_instruments` | `news_item_id` FK, `instrument_id` FK | Many-to-many; unique on the pair. |
| `sentiment_snapshots` | `instrument_id`, `as_of`, `score`, `source`, `sample_size` | No vendor selected yet (BLOCKING_DECISIONS.md #1) — modeled so a future vendor needs no migration. |
| `macro_observations` | `series_code` (free-text, indexed), `as_of`, `value`, `source` | Unique on `(series_code, as_of, source)`. Free-text code, not a closed enum — the tracked-series set is expected to grow. |
| `market_regime_snapshots` | `as_of` (unique), `classification` (enum), `vix_proxy_level`/`percentile`/`rate_of_change`, `breadth_pct_above_sma50`, `inputs_snapshot` (JSON) | One row/day; `inputs_snapshot` captures the exact numbers behind the classification so "why was today conservative" is always answerable from stored data. |
| `data_quality_events` | `subject_type`, `subject_id` (generic, no FK — same reasoning as `audit_events.ref_id`), `instrument_id` (nullable FK), `status` (enum), `detail`, `detected_at` | Indexed on `(subject_type, subject_id)`. |

## 4. Agent & committee orchestration (`models/agents.py`)

Schema only this pass — no live Anthropic calls are wired up yet ("do not
integrate external providers yet"); the seed script populates one
synthetic, realistic committee run so the read API has real data.

| Table | Key fields | Notes |
|---|---|---|
| `agent_definitions` | `role` (enum, unique — 8 committee roles), `name`, `description` | Role identity, independent of which prompt version is active. |
| `agent_versions` | `agent_definition_id` FK, `version_label`, `prompt_version_id` FK (nullable), `model_name`, `is_active` | Unique on `(agent_definition_id, version_label)` — per-role prompt/model versioning (changing the Bear Analyst's prompt doesn't re-version the other 7). |
| `committee_sessions` | `instrument_id` FK, `triggered_by` (free text, e.g. `PREMARKET_JOB`/`MANUAL`), `status` (enum), `started_at`/`completed_at` | One full committee run for one instrument. |
| `agent_runs` | `committee_session_id` FK, `agent_version_id` FK, `status` (enum), `input_snapshot`/`output_snapshot` (JSON), `started_at`/`completed_at`, `error_detail` | One role's single call within a session — the exact evidence bundle and structured response, for audit reconstruction without re-querying any vendor. |
| `agent_evidence_links` | `agent_run_id` FK, `evidence_type` (generic), `evidence_id` (generic UUID) | Indexed on `(agent_run_id, evidence_type)`. Which specific evidence rows a run actually cited (Bull/Bear must cite evidence, not just assert a view). |
| `agent_opinions` | `agent_run_id` FK (unique — 1:1), `stance` (nullable), `structured_output` (JSON) | Split out from `agent_runs.output_snapshot` for queryability ("show me every BEARISH opinion this week") without JSON parsing. |

`ModelCallRecord.agent_run_id` (§7 below) is the reverse pointer from a
committee run to its underlying LLM call(s) — kept one-directional rather
than a second FK back on `agent_runs`, since one run can legitimately
produce more than one call record (e.g. a retry after malformed structured
output).

## 5. Recommendations (`models/recommendations.py`)

Splits the MVP's single mutable-ish `Recommendation` row into a **stable
identity** plus **immutable, append-only version snapshots** — "preserve
recommendation snapshots so later model changes cannot rewrite history" is
the direct design driver.

| Table | Key fields | Notes |
|---|---|---|
| `recommendations` | `instrument_id` FK, `watchlist_item_id` FK (nullable), `opened_at`, `status` (enum) | The stable identity — "our current call on this instrument." Content lives on the latest version, never here. |
| `recommendation_versions` | `recommendation_id` FK, `committee_session_id` FK (nullable), `version_number`, `action` (enum), `confidence` (enum), `score` (nullable), `rationale`, `deterministic_inputs_snapshot` (JSON), `generated_at` | Unique on `(recommendation_id, version_number)`. **Never updated once written** — a recompute creates the next version number, it never mutates a prior one. |
| `recommendation_levels` | `recommendation_version_id` FK, `kind` (enum: `ENTRY\|STOP\|TARGET\|TRAILING`), `price`, `basis` (human-readable explanation) | Entry/stop/target/trailing prices for one version. |
| `recommendation_status_events` | `recommendation_id` FK, `from_status`/`to_status` (enum, nullable from), `reason`, `occurred_at` | Append-only audit trail for `recommendations.status` transitions, guarded by `assert_transition_allowed` against `RECOMMENDATION_TRANSITIONS`. |
| `confidence_calibration_records` | `confidence_band` (enum), `period_start`/`period_end`, `sample_size`, `hit_rate` (nullable) | Populated once a real sample of closed, outcome-tracked recommendations exists. |

## 6. Portfolio & execution (`models/execution.py`)

Generalizes the MVP's Alpaca-specific paper trading into broker-agnostic
`Account`/`Order`/`Execution` — a manual journal account and a paper-broker
account are two rows of the same shape.

| Table | Key fields | Notes |
|---|---|---|
| `accounts` | `owner_user_id`, `account_type` (enum: `MANUAL\|PAPER_ALPACA`), `name`, `base_currency`, `starting_cash`, `broker_account_ref` (identifier only, never a credential), `is_active` | |
| `cash_ledger` | `account_id` FK, `entry_type` (enum), `amount` (`Numeric(18,6)`, signed), `related_order_id`/`related_execution_id` (nullable FK), `occurred_at`, `idempotency_key` (unique, nullable) | **Append-only.** Current cash = `starting_cash + sum(amount)` — never stored directly. Indexed on `(account_id, occurred_at)`. |
| `positions` | `account_id` FK, `instrument_id` FK, `quantity` (`Numeric(20,8)` — fractional shares), `avg_cost`, `opened_at` | Unique on `(account_id, instrument_id)`. The *current* aggregate — never independently authoritative, kept in sync with `position_lots` by `_apply_fill()`. |
| `position_lots` | `position_id`/`account_id`/`instrument_id` FK, `opened_execution_id` FK, `quantity_opened`, `quantity_remaining`, `cost_basis_price`, `opened_at`, `closed_at` (nullable) | FIFO cost-basis tracking. A BUY opens a new lot; a SELL consumes open lots oldest-first (`_apply_fill()`), decrementing `quantity_remaining` and setting `closed_at` once a lot empties. Indexed on `(account_id, instrument_id, closed_at)`. `sum(quantity_remaining)` for a position must equal `positions.quantity` — checked by `tests/test_invariants.py` and `GET /api/v1/orders/reconciliation/{account_id}`. |
| `orders` | `account_id`/`instrument_id` FK, `side`/`order_type`/`time_in_force` (enums), `quantity`, `limit_price`/`stop_price` (nullable), `status` (enum), `broker_order_id`, `submitted_at`/`filled_at`/`canceled_at`, `linked_recommendation_version_id` FK (nullable), `idempotency_key` (unique, nullable) | `DRAFT` until `POST .../confirm` (ADR-014, principle 11 gate) — no broker call happens for either account type this pass. |
| `order_legs` | `order_id` FK (unique), `role` (enum: `PRIMARY\|STOP_LOSS\|TAKE_PROFIT`), `bracket_group_id` (nullable) | Models bracket/OCO relationships without assuming a broker natively supports them — orders sharing a `bracket_group_id` are one unit in our own domain logic regardless of broker linkage. |
| `executions` | `order_id` FK, `quantity`, `price`, `executed_at`, `broker_execution_id` (unique, nullable) | Append-only fill fact. `broker_execution_id` is the idempotency key for a replayed broker fill event. Indexed on `(order_id, executed_at)`. |
| `fees` | `execution_id` FK, `fee_type` (enum), `amount` | |
| `trades` | `account_id`/`instrument_id` FK, `status` (enum), `opened_at`/`closed_at`, `quantity`, `realized_pnl` (nullable) | A round-trip: flat → position → flat. |
| `trade_theses` | `trade_id` FK, `linked_recommendation_id` FK (nullable), `thesis_text`, `catalyst_text`, `original_stop_price`, `is_intact` | An add-on proposal's no-average-down precondition checks whether the thesis is still `is_intact` and whether a *new* catalyst exists beyond it. |
| `trade_notes` | `trade_id` FK, `note_text` | |
| `trade_attachments` | `trade_note_id` FK, `file_name`, `content_type`, `size_bytes`, `storage_ref` (nullable) | Metadata only — no file upload/storage exists yet. |
| `portfolio_snapshots` | `account_id` FK, `as_of`, `cash`, `market_value`, `total_equity` | Unique on `(account_id, as_of)`. |
| `risk_snapshots` | `account_id` FK, `as_of`, `gross_exposure_pct`, `largest_position_pct`, `sector_concentration` (JSON), `correlation_flag`, `regime_snapshot_id` FK (nullable) | |

## 7. Outcomes & learning (`models/learning.py`, `models/backtest.py`)

| Table | Key fields | Notes |
|---|---|---|
| `recommendation_outcomes` | `recommendation_id` FK (unique — 1:1), `classification` (enum), `linked_trade_id` FK (nullable), `matched_at`, `realized_pnl`, `r_multiple`, `computed_at` | **Computed, never self-reported** — what the user actually did about a recommendation, plus its eventual result. |
| `hypothetical_trade_outcomes` | `recommendation_id` FK, `simulated_entry_price`/`exit_price` (nullable), `simulated_exit_reason`, `simulated_pnl_pct`, `computed_at` | "What would have happened" for an `IGNORED` recommendation — clearly simulated, never conflated with a real `Trade`. |
| `trade_reviews` | `trade_id` FK, `rating` (enum, nullable), `review_text`, `reviewed_at` | |
| `performance_snapshots` | `account_id` FK, `period_start`/`period_end`, `realized_pnl`, `win_rate`, `avg_r_multiple`, `max_drawdown_pct` | Unique on `(account_id, period_start, period_end)`. |
| `benchmark_snapshots` | `benchmark_ticker`, `period_start`/`period_end`, `return_pct` | Unique on `(benchmark_ticker, period_start, period_end)`. |
| `strategy_definitions` | `owner_user_id`, `name`, `description` | Stable identity — mirrors `agent_definitions`/`agent_versions`'s shape. |
| `strategy_versions` | `strategy_definition_id` FK, `config` (JSON), `status` (enum: `PROPOSED\|ACTIVE\|REJECTED\|SUPERSEDED`), `decided_at`, `decision_comment` | Unchanged governance mechanism from the shipped MVP (principle 16) — now a version under a `strategy_definitions` parent. |
| `scoring_weight_versions` | `strategy_version_id` FK, `signal_name`, `weight` | Unique on `(strategy_version_id, signal_name)`. A queryable projection of the weights inside `strategy_versions.config`'s JSON — the JSON stays the source of truth for `services/scoring.py`; this table exists for cross-version queries. |
| `model_change_proposals` | `owner_user_id`, `subject_type`, `subject_ref_id` (generic), `description`, `status` (enum), `proposed_at` | Principle 16 generalized beyond scoring weights — a prompt-version change or a committee pre-filter change routes through here instead. |
| `model_change_approvals` | `proposal_id` FK, `decision` (enum), `comment`, `decided_at` | |
| `backtest_runs` | `strategy_version_id` FK, `date_range_start`/`date_range_end`, `parameters` (JSON), `results_summary` (JSON) | Reshaped from the MVP's integer-keyed table (ADR-043) — same principle-14 guarantees (no look-ahead, no survivorship bias, no unrealistic fills). |
| `backtest_trades` | `backtest_run_id` FK (indexed), `instrument_id` FK, `entry_date`/`price`, `exit_date`/`price`, `quantity`, `pnl_usd`/`pnl_pct`, `exit_reason` (enum) | The refinement brief's explicit ask: the trade log inside `results_summary`'s JSON is now **also** normalized into real, queryable rows, generated from the same simulation write — never a second independent source of truth. |

## 8. Operations (`models/operations.py`, `models/audit_event.py`)

| Table | Key fields | Notes |
|---|---|---|
| `alerts` | `owner_user_id`, `instrument_id` FK (nullable), `severity`/`status` (enums), `title`, `detail`, `triggered_at` | |
| `alert_deliveries` | `alert_id` FK, `channel` (enum), `status` (enum), `delivered_at` | In-app is the only channel actually used (BLOCKING_DECISIONS.md #9) — modeled generically so a future channel needs no migration. |
| `job_runs` | `job_name` (indexed), `status` (enum), `started_at`/`completed_at`, `error_detail`, `idempotency_key` (unique, nullable) | Premarket/intraday/EOD scheduled-job runs. `idempotency_key` (e.g. `"premarket:2026-08-04"`) prevents the same day's job double-running. |
| `prompt_templates` | `agent_role` (enum, nullable), `name` | |
| `prompt_versions` | `prompt_template_id` FK, `version_label`, `body`, `status` (enum) | Unique on `(prompt_template_id, version_label)`. |
| `model_call_records` | `agent_run_id` FK (nullable, indexed), `prompt_version_label`, `model`, `input_tokens`/`output_tokens`, `cost_usd`, `latency_ms`, `stop_reason`, `response_excerpt` (≤500 chars) | Supersedes `LLMCallLog` — **deliberately narrower**: token/cost/latency metadata and a short truncated excerpt only, **no full request/response payload** ("no secrets or unnecessary private prompt content"). Evidence text is already durably stored at its source (`news_items`, etc.) and linked via `agent_evidence_links`, so it isn't duplicated here. |
| `audit_events` | `record_type`, `ref_id` (generic, not a FK), `snapshot` (JSON), `created_at` | **Unchanged from the shipped MVP** — the one Phase 1-7 table kept as-is (ADR-043's single exception). |

## Current-state derivation

Every "current" figure in this system is computed, never stored as the
primary value:

- **Cash**: `accounts.starting_cash + sum(cash_ledger.amount)`.
- **Position quantity/cost**: the `positions` row, kept in sync with
  `position_lots` by `routers/orders.py::_apply_fill()` on every fill —
  never independently recomputed from scratch on read.
- **Watchlist membership state, recommendation content, strategy config**:
  always the *latest* child row (`recommendation_versions`,
  `strategy_versions`), never a mutated parent.

## Historical: Phase 1-7 schema (retired, ADR-043)

The shipped MVP (Phases 1-7) ran a 9-table, integer-PK, SQLite-then-Postgres
schema: `symbols`, `price_bars`, `indicators`, `paper_portfolios`,
`paper_orders`, `audit_events`, `strategy_versions`, `recommendations`,
`llm_call_logs`. Phase 8 dropped and recreated all of these except
`audit_events` (kept verbatim) as part of the wholesale domain-model
replacement described above — see ADR-043 in `docs/DECISIONS.md` for the
full reasoning, and `apps/api/alembic/versions/ece90645a84b_*.py` for the
exact migration (its `downgrade()` recreates the original 9-table shape
byte-for-byte, so the old schema is fully recoverable if ever needed).
