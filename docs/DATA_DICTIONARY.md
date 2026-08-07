# Data Dictionary

**Phase 8 (current)** replaced the shipped MVP's 9-table schema wholesale
with a ~70-entity domain model spanning 13 bounded contexts (ADR-043) — see
"Historical: Phase 1-7 schema" at the bottom of this document for what
existed before and exactly what was retired. Three table names survive the
rewrite with reshaped columns (`recommendations`, `backtest_runs`,
`audit_events`); everything else is new. Every table uses a UUID primary
key (`sa.Uuid(as_uuid=True)`, `UUIDPkMixin`) and UTC timestamps
(`sa.DateTime(timezone=True)`). **Revision Prompt R3** (section 9 below)
additively extends this with ~35 more tables (decision taxonomy,
investment thesis, earnings evidence, morning plan, order authority,
strategy governance, ADR-050) plus two backward-compatible column adds
on existing tables — no table is dropped, renamed, or has a column
removed. **Revision Prompt 4** (section 10 below) additively extends the
market-evidence tables with `usable_at` point-in-time cutoff columns, two
new columns each on `earnings_consensus_snapshots`/`earnings_guidance_items`,
two new columns on `corporate_actions`, two new enum values on
`earnings_timing_category`, and two new generic-ledger tables
(`earnings_event_corrections`, `provider_ingestion_records`) — the same
additive discipline, no table dropped or column removed.

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

## 9. Revision Prompt R3 — decision taxonomy, investment thesis, earnings evidence, morning plan, order authority, strategy governance

Purely additive (ADR-050): every table below is new, and the two
existing-table changes are backward-compatible column adds with a
backfill default for pre-existing rows (`recommendations.mode` ->
`TACTICAL`, `strategy_definitions.family` -> `GENERIC`).

**Decision taxonomy** (`models/recommendations.py`, `models/enums.py`)

| Table/column | Key fields | Notes |
|---|---|---|
| `recommendations.mode` (new column) | `RecommendationMode` enum (`INVESTMENT`\|`TACTICAL`) | ADR-046: a symbol may have both an Investment and a Tactical `Recommendation` row at once — always two separate rows, never one row with two lanes. |
| `recommendation_versions.lane_action`/`horizon_days_min`/`horizon_days_max`/`review_date` (new columns) | `lane_action` is a plain `String(30)`, not a native enum | A single column can't cleanly type-check against "one of two enums (`InvestmentAction`/`TacticalAction`, `policy/recommendation_modes.py`) depending on another column's value" in Postgres without a trigger — validated at the API layer instead, the same trade-off this project already documents for mode-conditional vocabularies. |
| `recommendation_invalidation_conditions` | `recommendation_version_id` FK, `condition_text` | One row per stated thesis-break/cancellation condition (DQ-1/DQ-2); append-only. |
| `recommendation_attributions` | `recommendation_version_id` FK, `mode`, `position_lot_id` FK (nullable), `trade_id` FK (nullable) | Links a `PositionLot`/`Trade` back to the exact recommendation version (and lane) that produced it — the mechanism behind "how are investment and tactical positions attributed if they share one broker symbol." |

**Investment thesis** (`models/investment_thesis.py`, new file)

| Table | Key fields | Notes |
|---|---|---|
| `investment_theses` | `recommendation_id` FK (unique, 1:1), `instrument_id` FK, `status` (`ThesisStatus`) | One per Investment-lane `Recommendation` — stable identity, mirrors `Recommendation`/`RecommendationVersion`'s split. |
| `investment_thesis_versions` | `investment_thesis_id` FK, `version_number` (unique together), `valuation_low`/`mid`/`high`, `thesis_text`, `horizon_days_min`/`max`, `review_date`, `generated_at` | Immutable once written. |
| `valuation_snapshots` | `investment_thesis_id` FK, `as_of`, `method`, `fair_value_low`/`mid`/`high`, `source`, `observed_at`, `ingested_at` | Independently-timestamped valuation refresh, distinct from the thesis version's own stated range. |
| `thesis_catalysts` / `thesis_risks` | `investment_thesis_version_id` FK, `catalyst_text`/`risk_text` | One row per catalyst/risk stated on a version. |
| `thesis_review_events` | `investment_thesis_id` FK, `reviewed_at`, `outcome`, `notes` | A review can conclude "still intact" with no status change at all — distinct from `thesis_status_history`. |
| `thesis_status_history` | `investment_thesis_id` FK, `from_status`/`to_status`, `reason`, `occurred_at` | Append-only, guarded by `THESIS_STATUS_TRANSITIONS`. |

**Earnings evidence** (`models/market_evidence.py`, extended)

| Table/column | Key fields | Notes |
|---|---|---|
| `earnings_events` (new columns) | `verified_date`, `exchange_local_date`, `timing_category` (`EarningsTimingCategory`), `verification_source`, `expected_report_period`, `confidence` — all nullable | HES-2 condition 1: event time is verified, not guessed. |
| `earnings_revisions.ingested_at` (new column) | server-default `now()` | The one missing provenance column on an already-right-shaped Phase 8 table — no redundant second table created. |
| `earnings_consensus_snapshots` | `earnings_event_id` FK, `as_of`, `consensus_eps`/`revenue`, `num_analysts`, `source`, `observed_at`, `ingested_at` | |
| `earnings_guidance_items` | `earnings_event_id` FK, `metric`, `guidance_low`/`high`, `period`, `issued_at`, `source` | |
| `earnings_actuals` | `earnings_event_id` FK, `metric`, `actual_value`, `reported_at`, **`usable_at`**, `source`, `ingested_at` | `usable_at` is the ground-truth field `policy/earnings_evidence.py` checks a pre-event snapshot's `evidence_cutoff` against. |
| `earnings_historical_gaps` | `instrument_id` FK, `earnings_event_id` FK (nullable), `gap_pct`, `session_date`, `source` | |
| `event_expected_move_snapshots` | `earnings_event_id` FK, `as_of`, `evidence_cutoff`, `atr_based_move_pct`/`historical_gap_move_pct`/`option_implied_move_pct` (nullable), `selected_expected_move_pct`, `calculation_version` | |
| `earnings_feature_snapshots` | `earnings_event_id` FK, `as_of`, `evidence_cutoff`, `is_pre_event` (always `true` this revision), 8 named `component_*` scores, `total_score`, `calculation_version`, `linked_actual_id` FK (nullable, to `earnings_actuals`) | Always pre-event — `PostEarningsConfirmationSnapshot` is the structurally separate post-event table, not a flag flip on this one. |
| `post_earnings_confirmation_snapshots` | `earnings_event_id` FK, `as_of`, `evidence_cutoff`, `results_gate_passed`/`guidance_gate_passed`/`market_reaction_gate_passed`, `all_gates_passed`, `notes` | HES-4's three independent gates, each recorded so a partial pass is never conflated with a full one. |

**Morning plan** (`models/morning_plan.py`, new file, ADR-047)

| Table | Key fields | Notes |
|---|---|---|
| `morning_plan_runs` | `job_run_id` FK (nullable), `plan_date` (indexed), `triggered_by`, `status` (`MorningPlanRunStatus`), `idempotency_key` (unique, nullable), `started_at`/`completed_at` | One scheduler invocation. |
| `morning_plan_versions` | `morning_plan_run_id` FK, `plan_date`, `version_label` (`PRELIMINARY`\|`FINAL`\|`AD_HOC`\|`CORRECTION`), `version_number`, `evidence_cutoff`, `generated_at`, `completeness_status` | Immutable once published — a rerun always adds a row (R3's required test). |
| `morning_plan_input_links` | `morning_plan_version_id` FK, `input_type`, `input_id` (generic, not a FK) | The lineage manifest — which evidence/recommendation rows a version was built from. |
| `morning_plan_sections` | `morning_plan_version_id` FK, `section_key` (`MorningPlanSectionKey`, unique with version), `display_order` | The fixed seven-section grouping (MDS-5). |
| `morning_plan_items` | `morning_plan_section_id` FK, `recommendation_version_id` FK (nullable), `display_order`, `headline` | Nullable FK so a Data Problems item (naming what failed) is representable too. |
| `morning_plan_quality_checks` | `morning_plan_version_id` FK, `check_name`, `passed`, `detail` (nullable) | Per-check detail behind `completeness_status`. |
| `morning_plan_delivery_events` | `morning_plan_version_id` FK, `channel` (`DeliveryChannel`), `status` (reuses `AlertDeliveryStatus`), `delivered_at` | `channel=COWORK` rows only ever exist for an already-published `FINAL` version (ADR-049) — enforced at the service layer. |

**Order authority** (`models/order_authority.py`, new file, ADR-048)

| Table | Key fields | Notes |
|---|---|---|
| `operating_mode_history` | `mode` (`OrderAuthorityMode`), `changed_by`, `changed_at`, `reason` | Append-only log of every operating-mode change. |
| `order_proposals` | `recommendation_version_id` FK, `account_id` FK, `instrument_id` FK, `mode`, `side`, `status` (`OrderProposalStatus`), `idempotency_key` (unique, nullable), `updated_at` | Stable identity, upstream of and distinct from `orders`. |
| `order_proposal_versions` | `order_proposal_id` FK, `version_number` (unique together), `order_type`, `quantity`, `limit_price`/`stop_price`, `time_in_force`, `max_notional`, `rationale` | Immutable once written. |
| `order_policy_evaluations` | `order_proposal_version_id` FK, `evaluated_at`, `requested_mode`, `authorized`, `denial_reason` | Append-only record of every `assert_order_authorized()` (R0) call and its outcome. |
| `order_approvals` | `order_proposal_version_id` FK, `approved_by`, `requested_at`, `decided_at`, `expires_at`, `status` (`OrderApprovalStatus`), `integrity_hash`, `updated_at` | `EXPIRED`/`INVALIDATED` are terminal — never transition back to `APPROVED` (R3's required test). |
| `approval_bound_fields` | `order_approval_id` FK (unique, 1:1), account/instrument/side/quantity/order_type/limit_price/stop_price/time_in_force/outside_hours/attached_legs/max_notional/recommendation_version_id | Immutable snapshot the parent approval's `integrity_hash` is computed over, in a fixed field order (`services/order_authority.py::compute_bound_fields_hash()`). |
| `approval_invalidations` | `order_approval_id` FK, `reason` (`ApprovalInvalidationReason`), `detail`, `invalidated_at` | Distinct from a rejection — the system unilaterally refusing to honor an approval. |
| `broker_submission_attempts` | `order_approval_id` FK, `attempted_at`, `environment_label`, `outcome` (`BrokerSubmissionOutcome`), `idempotency_key` (unique, nullable), `detail` | Schema-only this revision — no code path writes `SUCCEEDED` for `LIVE` ("do not add a live broker submission endpoint yet"). |
| `execution_kill_switch_events` | `activated_by`, `activated_at`, `deactivated_at` (nullable), `reason` | Append-only (OA-9). |
| `broker_environment_attestations` | `environment_label`, `account_id` FK (nullable), `broker_endpoint`, `attested_by`, `attested_at` | The recorded `(environment, account, broker_endpoint)` triple OA-6 requires be unambiguous. |

**Strategy governance** (`models/learning.py`, `models/identity.py`, extended)

| Table/column | Key fields | Notes |
|---|---|---|
| `strategy_definitions.family` (new column) | `StrategyFamily` (`INVESTMENT_QUALITY`\|`EARNINGS_PRE_EVENT`\|`EARNINGS_POST_CONFIRMATION`\|`GENERIC`) | Backfilled to `GENERIC` for pre-existing rows. |
| `strategy_eligibility_snapshots` | `strategy_version_id` FK, `instrument_id` FK, `as_of`, `eligible`, `reason` | |
| `decision_policy_versions` | `owner_user_id`, `version_label`, `config` (JSON), `status` (reuses `StrategyVersionStatus`), `decided_at`, `decision_comment` | |
| `risk_policy_versions` | `risk_policy_id` FK, the same five numeric fields as `risk_policy`, `changed_at` | Append-only snapshot history paralleling the singleton, mutable-in-place `risk_policy` row — `risk_policy` itself stays unversioned by design. |

## 10. Revision Prompt 4 — point-in-time evidence layer

Purely additive. Every column below is nullable (or, for the one
NOT-NULL boolean, backfilled with a `server_default`) so no pre-existing
row is invalidated.

| Table/column | Key fields | Notes |
|---|---|---|
| `earnings_timing_category` (enum, new values) | `TIME_NOT_SUPPLIED`, `DATE_UNCONFIRMED` added alongside the existing `BEFORE_OPEN`/`AFTER_CLOSE`/`DURING_MARKET`/`UNKNOWN` | Two more precise "we don't know" states than the original catch-all `UNKNOWN`, which is kept, unremoved, for backward compatibility. Postgres has no `ALTER TYPE ... DROP VALUE`, so a downgrade leaves the two new values in the type (harmless — nothing references them once the migration's own columns are dropped). |
| `news_items.usable_at` (new column, nullable) | point-in-time cutoff field | |
| `earnings_guidance_items.usable_at`/`.guidance_midpoint`/`.units` (new columns, nullable) | cutoff field + the two remaining required guidance fields ("metric, period, low/high/midpoint, units, and source") | |
| `earnings_consensus_snapshots.usable_at`/`.eps_dispersion` (new columns, nullable) | cutoff field + analyst estimate dispersion, when the provider supplies it | |
| `earnings_revisions.usable_at` (new column, nullable) | cutoff field | |
| `fundamentals_snapshots.usable_at` (new column, nullable) | cutoff field | |
| `corporate_actions.invalidates_earnings_interpretation`/`.note` (new columns) | `invalidates_earnings_interpretation` boolean, backfilled `false`; `.note` nullable text | A corporate event (merger, large special dividend) that makes an "ordinary" earnings beat/miss interpretation meaningless for that print — a flag the earnings data-quality gates read, set explicitly by a human or a future rule, never inferred automatically. |
| `earnings_event_corrections` (new table) | `earnings_event_id` FK, `version_number`, `corrected_field`, `previous_value`, `new_value`, `corrected_at`, `source`, `alert_id` FK (nullable, to `alerts`) | Append-only. A calendar-data provider revising an already-ingested event's date/timing writes a new row here (never a silent overwrite) plus a linked `Alert`. |
| `provider_ingestion_records` (new table) | `subject_type`, `subject_id` (generic, not a FK — same shape as `audit_events`/`data_quality_events`), `source`, `provider_record_id`, `revision_id`, `raw_payload_hash`, `ingested_at` | The generic "raw provider payload" ledger — one table spans every evidence type rather than adding a hash/record-id/revision-id column to each one individually (ADR-015's reasoning applied again). `raw_payload_hash` is retained only where the provider's terms permit; `NULL` otherwise, never a fabricated placeholder. |

**Provider interfaces** (`providers/*.py`, not a schema change but
documented here since they're this revision's other half): 15 Protocol
interfaces — `InstrumentReferenceProvider`, `MarketQuoteProvider`,
`HistoricalBarsProvider`, `CorporateActionsProvider`, `NewsProvider`,
`VolatilityIndexProvider`, `BrokerCapabilityProvider` (all backed for
real by Alpaca, `providers/alpaca_evidence.py`), and
`FundamentalsProvider`, `EarningsCalendarProvider`,
`EarningsConsensusProvider`, `AnalystRevisionProvider`,
`CompanyGuidanceProvider`, `OfficialFilingProvider`, `MacroProvider`,
`OptionsExpectedMoveProvider` (all synthetic/fixture-backed,
`providers/synthetic_evidence.py` — no vendor contracted,
docs/BLOCKING_DECISIONS.md #1/#2 remain open; "do not purchase a paid
service" is this revision's own explicit instruction). Every interface
defines its own capability-metadata model and its own
`NotConfigured`/`Unavailable` exception classes — capability and failure
state are never shared across interfaces even where one vendor
(Alpaca) implements several of them in the same class.

## 11. Revision Prompt 5 — deterministic dual-lane analytics and earnings feature engine

Purely additive: two new tables, one new enum, no changes to any
existing column.

| Table/column | Key fields | Notes |
|---|---|---|
| `feature_component_status` (new enum) | `PASS`, `FAIL`, `MISSING_DATA`, `CAPABILITY_UNAVAILABLE`, `INSUFFICIENT_HISTORY` | `INSUFFICIENT_HISTORY` was added in a second, follow-up migration (`ad4b61d69412`) after the first end-to-end demo run raised a real `ValueError` — `services/analytics.py` and `services/earnings_score.py` already emitted this status for short input series, but the enum created by the schema migration (`b5b705be657a`) didn't have it yet. `CAPABILITY_UNAVAILABLE` (structural data-entitlement gap, e.g. no intraday feed) and `INSUFFICIENT_HISTORY` (data exists, just not enough of it yet) are kept as two distinct states, never collapsed into `MISSING_DATA`. |
| `feature_component_results` (new table) | `subject_type`, `subject_id` (generic, not a FK — the same ADR-015 shape as `audit_events`/`data_quality_events`/`provider_ingestion_records`), `component_key`, `component_order`, `value` (nullable `Numeric(20,6)`), `status`, `source`, `detail`, `calculation_version`, `as_of` | One generic table for every scored component across all three lanes (`subject_type` is the parent snapshot's class name: `EarningsFeatureSnapshot`, `InvestmentQualityFeatureSnapshot`, or `PostEarningsConfirmationSnapshot`). Append-only — a re-scoring pass writes new rows against a new parent id, never edits a prior result. This is why the diagnostic UI (`/api/v1/feature-diagnostics/*`) only needs one query shape regardless of which lane produced the components. |
| `investment_quality_feature_snapshots` (new table) | `instrument_id` FK, `as_of`, `evidence_cutoff`, `calculation_version`, `hard_disqualified` (bool, default `False`), `disqualification_reason` (nullable text) | The Investment lane's parent snapshot. Deliberately holds no single opaque score — its 9 component scores live exclusively in `feature_component_results`; `hard_disqualified` is a separate, explicit veto flag that no combination of strong components can override (see ADR-050). |

**`EarningsFeatureSnapshot`'s pre-existing fixed `component_*` columns
are now superseded, not migrated.** That table (added before this
revision) has 8 named columns (`component_price_trend`,
`component_analyst_revisions`, `component_options_skew`, etc.) from an
earlier, looser placeholder factor set. Revision Prompt 5 specifies a
different, precisely-named 8-component score (`PRICE_ABOVE_EMA20`,
`RS_20D_VS_SPY`, `MOMENTUM_5D`, `VOLUME_ACCUMULATION`,
`FORECAST_EPS_GROWTH`, `ANALYST_COVERAGE`, `SPY_ABOVE_EMA20`,
`PRIOR_GAP_BIAS`) that doesn't map onto those old column names.
`services/persist_feature_results.py::persist_tactical_score()` writes
`total_score`/`calculation_version` to `EarningsFeatureSnapshot` (still
useful, unchanged fields) but leaves every `component_*` column null,
writing the named component detail exclusively to
`feature_component_results` instead. The old columns are left in place
rather than dropped — no data they held was ever real (Phase 8 was a
schema-first build), and dropping them is a mechanical follow-up, not a
blocking issue.

**New services** (`services/*.py`, not a schema change but documented
here since they're this revision's other half): `analytics.py` (SMA,
EMA, RSI, MACD, ATR, normalized ATR, realized volatility, rolling
volume, relative strength, support/resistance, trend, momentum,
liquidity, correlation — pure Python + `Decimal`, no numpy/pandas
runtime dependency), `market_regime.py`, `earnings_score.py` (the
tactical 8-component score), `investment_quality.py` (the Investment
lane's 9 components), `expected_move.py`, `baseline_eligibility.py` (the
9-condition AND gate), `post_earnings_confirmation.py` (the three-gate
post-event confirmation), and `persist_feature_results.py` (the one
write path from any lane's pure compute result into the schema above).

## 12. Revision Prompt 6 — evidence-bound Investment Committee and Tactical Trading Desk

Purely additive: 17 new `agent_role` enum values and one nullable
`committee_sessions.mode` column. No new tables — the existing agent/
committee schema (`AgentDefinition`/`AgentVersion`/`CommitteeSession`/
`AgentRun`/`AgentEvidenceLink`/`AgentOpinion`, ADR-038) and the existing
Investment-thesis/Recommendation schema (R3) already had everything this
revision's orchestration needed; nothing was schema-first this time.

| Table/column | Key fields | Notes |
|---|---|---|
| `agent_role` (enum, +17 values) | 8 Investment roles (`BUSINESS_QUALITY_ANALYST` .. `INVESTMENT_CIO`) + 9 Tactical roles (`MARKET_INTELLIGENCE_ANALYST` .. `TRADING_CIO`) | ADR-038's original 8 (`BULL`..`CIO`) — a single, lane-agnostic committee design — are kept, unremoved, for backward compatibility with already-seeded fixture rows; no new code writes them. |
| `committee_sessions.mode` (new column, nullable `recommendation_mode`) | `INVESTMENT` or `TACTICAL` | Nullable because it predates this column — rows seeded under the original 8-role design have no lane to report. Reuses the existing `RecommendationMode` enum rather than a second lane concept. |

**No new tables were needed** for the Agent Contract's 15 required
fields — every field lands in an existing column:

| Agent Contract field | Where it's stored |
|---|---|
| agent and prompt version | `AgentDefinition.role` + `AgentVersion.version_label` |
| recommendation lane | `CommitteeSession.mode` |
| evidence cutoff | `AgentRun.input_snapshot['evidence_cutoff']` |
| evidence ids | `AgentEvidenceLink` rows (one per cited id) |
| factual claims mapped to evidence ids | `AgentOpinion.structured_output['factual_claims']` (schema-validated — see below) |
| deterministic feature ids | `AgentRun.input_snapshot['deterministic_feature_ids']` |
| thesis, strongest supporting/contradictory evidence, risks, missing information, invalidation conditions, categorical stance, evidence completeness, calibration status | `AgentOpinion.structured_output` (the full validated contract JSON) |
| model, token, latency, cost metadata | `ModelCallRecord` (one row per `AgentRun`) |

**`schemas/agent_contract.py`** (not a schema change, but the other half
of "every output must include..."): `AgentContractOutput` — the shared
15-field pydantic shape every one of the 17 roles' output is validated
against before persistence, with a `model_validator` that rejects any
factual claim citing an evidence id the agent didn't itself declare.
`InvestmentCioOutput`/`TradingCioOutput` extend it with each CIO's
lane-specific required fields (action, horizon/window, thesis-break or
entry-invalidation conditions, minority opinion) — two separate schemas,
never one shape with optional fields for both lanes, so the two
conclusions cannot be structurally confused (ADR-052).

**New services**: `services/committee_roles.py` (the 17-role registry:
identity, lane, CIO flag, focus text — no computation), `services/llm_cost.py`
(re-created; retired at Phase 8 along with the rest of the shipped MVP's
business logic), `services/agent_runner.py` (the one generic
execution path every role goes through — cost ceiling, timeout,
fallback, forced structured tool output), `services/committee_orchestrator.py`
(runs a full committee, enforces the deterministic-veto override in
code, writes `Recommendation`/`RecommendationVersion`/
`RecommendationInvalidationCondition` and, for a new `INVEST_BUY`/
`INVEST_ADD`, an `InvestmentThesis` — DQ-1's "documented thesis,
valuation logic, horizon, review date, and thesis invalidation"), and
`services/side_by_side.py` (deterministic, templated — never an LLM
call — comparison text).

## 13. Revision Prompt 7 — decision policy, risk manager, and hybrid earnings recommendation engine

Purely additive: 16 new columns across two existing tables, no new
tables. The 9-step pipeline itself needed no new schema — it reads and
writes entirely through R3's `Recommendation`/`RecommendationVersion`/
`RecommendationInvalidationCondition`/`OrderProposal`/`OrderProposalVersion`
and Revision Prompt 6's committee schema.

| Table/column | Key fields | Notes |
|---|---|---|
| `order_proposal_versions` (10 new columns) | `environment` (nullable `environment_label`, reused), `outside_hours` (bool, default `False`), `attached_legs` (JSON, default `{}`), `max_slippage_bps`, `valid_from`/`expires_at` (this proposal's own validity window — distinct from the later `OrderApproval.expires_at`), `risk_policy_version`, `data_cutoff`/`quote_observed_at` (point-in-time provenance), `requires_approval` (bool, default `True`) | Fills out the "ORDER PROPOSAL FIELDS" list R3's original columns (`order_type`, `quantity`, `limit_price`, `stop_price`, `time_in_force`, `max_notional`, `rationale`) didn't yet carry. |
| `risk_policy`/`risk_policy_versions` (6 new columns each) | `earnings_risk_budget_pct` (default `0.0025` = 0.25%), `earnings_risk_budget_max_pct` (default `0.0050` = 0.50%, HES-3's absolute hard ceiling — enforced in code by `PATCH /api/v1/settings/risk-policy`, not just documented), `earnings_max_position_pct` (default `0.1500`), `earnings_max_sector_pct` (default `0.2500`), `earnings_max_concurrent_trades` (default `3`), `earnings_slippage_bps` (default `5.0000`) | Deliberately separate from the general-purpose `risk_budget_pct`/`max_position_pct`/etc. above — HES-3's own text is explicit these earnings-specific numbers are "materially smaller than the standard" general ones, never a replacement for them. Same fractional convention as the existing fields (`0.0025` = 0.25%); `services/position_sizing.py` takes whole-number percent and the pipeline converts at the boundary. |

**A pre-existing gap fixed while extending this area:** `RiskPolicyVersion`'s
own docstring promised "every time `PATCH /api/v1/settings/risk-policy`
changes a field, this revision's service layer also writes one of these
rows" (R3), but the actual R3 handler never did. Fixed as part of this
revision's own `PATCH` extension — every risk-policy update now writes
a `RiskPolicyVersion` snapshot, honoring what R3's schema always
intended.

**New services** (`services/*.py`, not a schema change but this
revision's other half): `services/hard_vetoes.py` (the 10 hard vetoes,
each producing a machine-readable code and a user-readable explanation
sentence), `services/position_sizing.py` (HES-3's
risk-budget-over-expected-move formula plus six sequential caps),
`services/gap_risk.py` (HES-5's gap-through-stop modeling — "a stop
order is never represented as a guarantee of the stop price," a literal
disclosure string on every result, not just a design intent),
`services/post_confirmation_gate.py` (HES-4/HES-6's post-confirmation
eligibility gate, with the adverse-gap no-averaging-down rule checked
independently of and prioritized over the three post-earnings
confirmation gates themselves), and `services/recommendation_pipeline.py`
(the 9-step orchestrator tying all of the above, plus Revision Prompt
5's deterministic features and Revision Prompt 6's committees, into one
call that always ends in exactly one outcome: a published action, a
published `NO_ACTION`, or — for a pre-flight veto — a published
`NO_ACTION` with no committee session at all).

**Investment/Tactical CIO output schemas extended** (`schemas/agent_contract.py`):
`InvestmentCioOutput` gained `preferred_accumulation_zone`, `tranche_plan`,
`proposed_max_allocation_pct`, and `why_investment_not_trade` — the
remaining "INVESTMENT ACTION PLAN" fields Revision Prompt 6's original
schema didn't yet require. No numeric valuation range (low/mid/high) is
requested from the CIO — that would be exactly the kind of calculation
an LLM must not produce (principle 6/7); `valuation_context` remains
qualitative narrative only, and a real numeric valuation model is a
documented limitation, not an oversight. These new fields, plus
Tactical's existing `setup_and_event_phase`/`key_catalyst`/`gap_risk`/
`liquidity_risk`, are persisted into `RecommendationVersion.deterministic_inputs_snapshot`
(`services/committee_orchestrator.py::_deterministic_inputs_snapshot()`)
and surfaced by the recommendation detail endpoints (API area 22).

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
