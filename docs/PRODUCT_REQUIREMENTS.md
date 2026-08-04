# Product Requirements

## Mission

TradingOS is a trustworthy, explainable decision-support application for a
retail investor doing swing trading (2–10 trading-day holding periods). It
validates and monitors a curated watchlist, gathers and grounds evidence
(technicals, fundamentals, catalysts, news, macro/regime), runs that
evidence through an investment committee and deterministic risk gates,
produces a concise actionable plan, tracks what the user actually does
(at any broker) against what was recommended, and improves over time through
evidence-based, human-approved review.

It is **not** a chatbot, **not** a guaranteed-profit system, and **not** an
unreviewed autonomous trading bot. See PROJECT_INSTRUCTIONS.md for the full
set of non-negotiable product principles that govern every design decision
in this repo.

## Persona

**One persona, described precisely because "personal system" can otherwise
mean anything:**

- A busy retail investor, sole user of the system.
- Starting paper capital: $10,000; aggressive risk tolerance, but capital
  preservation is a hard objective, not a soft preference — a large,
  avoidable drawdown is a worse outcome than a missed opportunity.
- Style: long-biased swing trading, 2–10 trading-day holding periods. Not a
  day trader, not a buy-and-hold investor.
- Wants a **concise** premarket plan they can read in a few minutes, not a
  wall of text — busy, checks the app once before market open, opportunistically
  during the day, and once after close.
- Places trades manually at their own broker (not necessarily Alpaca) today;
  open to connecting a paper broker for tracking convenience, uninterested in
  ever routing a live order through this system (principle 10 makes that
  moot anyway).
- Wants evidence-backed reasoning (news, earnings, sentiment, technicals,
  macro, VIX/regime, portfolio-level risk) behind every call, with an
  honestly-stated confidence — not a black-box score.
- Reviews performance periodically and expects the system's own track record
  (recommendation-vs-reality) to be as visible and auditable as their own.

## Jobs to be done

1. **"Tell me, before the bell, what actually deserves my attention today
   from my watchlist — and what doesn't."** (Premarket plan, watchlist
   tiers, deterministic pre-filter.)
2. **"When something looks interesting, show me the real case for and
   against it, not just a score."** (Investment committee — Bull/Bear/
   Technical/Fundamental/Macro debate, CIO synthesis.)
3. **"Tell me exactly how much to risk, where to get out, and why — before I
   place anything."** (Position sizing, stops/targets, risk gates.)
4. **"Stop me from doing something dumb under stress"** — averaging down
   without a new reason, oversizing into a speculative name, ignoring an
   earnings landmine, buying into elevated volatility without adjusting risk.
   (Deterministic gates, principle 1/capital preservation.)
5. **"Let me log what I actually did, wherever I did it, and keep my
   portfolio picture accurate."** (Manual trade journal, reconciliation.)
6. **"While I'm holding something, tell me if anything's changed enough that
   I should act."** (Active trade monitor, intraday alerts.)
7. **"At the end of the day/week, show me how I'm actually doing — and
   whether the system's own calls were any good."** (Performance dashboard,
   recommendation-vs-reality tracking.)
8. **"Let the system get better over time, but never without me seeing the
   evidence and approving it."** (Backtesting, walk-forward, versioned
   strategy governance — principle 16, unchanged mechanism from the shipped
   MVP.)

## Functional requirements

Grouped by the 15 required product capabilities from the refinement brief.
Each `FR-*` id is referenced from docs/UX_MAP.md (where it's exposed) and
docs/ARCHITECTURE.md (which bounded context owns it).

### Market regime and VIX analysis (FR-01–FR-03)
- **FR-01.** Compute a configurable volatility-regime classification from
  VIX(-proxy) level, percentile rank (trailing window, configurable), rate
  of change, and — if a term-structure proxy is available — its slope, plus
  price/breadth confirmation (e.g., % of Tier 1 names above their own
  SMA_50). Regime is one of a small enumerated set (e.g. `CALM`,
  `ELEVATED`, `STRESSED`) — never a raw VIX number alone.
- **FR-02.** Regime **adjusts** cash-allocation ceiling and per-trade risk
  budget (tighter in `STRESSED`, looser in `CALM`). Regime **never**
  independently triggers a BUY/SELL — this is enforced structurally: the
  regime module has no code path that writes a `Recommendation`, only one
  that constrains the risk-gate module's outputs.
- **FR-03.** Every regime classification is snapshotted (inputs + output +
  timestamp) and visible to the user — "why the plan is more conservative
  today" must always be answerable from stored data, not re-derived.

### Watchlist management (FR-04–FR-06)
- **FR-04.** A `Watchlist` entity with tiers (Tier 1 = the 48-symbol list
  today; the schema supports more tiers without a migration). Each
  membership row carries a configurable monitoring frequency (e.g. daily
  full evidence pull vs. weekly).
- **FR-05.** Adding a symbol to a watchlist tier always routes through
  symbol validation (FR-07) first — a symbol can't be a watchlist member
  without a validation record, resolved or quarantined.
- **FR-06.** Watchlist tier/frequency changes are audited (principle 9) —
  who/what changed a tier and when.

### Symbol validation (FR-07–FR-09)
- **FR-07.** For every raw ticker string entered (starting with the Tier 1
  list), resolve exchange, security type, active/inactive status, and
  canonical symbol against the configured reference source
  (BLOCKING_DECISIONS.md #7). Preserve the user-entered raw string
  regardless of outcome.
- **FR-08.** Classify each resolution as `RESOLVED`, `AMBIGUOUS` (multiple
  candidates — list them), or `QUARANTINED` (not found, inactive, or not a
  supported security type) with a human-readable reason string. A
  `QUARANTINED` symbol is visibly flagged everywhere it would otherwise
  appear (watchlist, premarket plan) — never silently dropped or silently
  treated as valid.
- **FR-09.** Re-validation is re-runnable on demand (a symbol can go from
  `ACTIVE` to inactive over time) and on a schedule (not just at watchlist-
  add time).

### Evidence gathering (FR-10–FR-15)
- **FR-10.** Technical evidence: existing indicator set (SMA/EMA/RSI/MACD/
  Bollinger/ATR), unchanged from the shipped MVP.
- **FR-11.** Fundamental evidence: a snapshot (sector, market cap, key
  ratios as available from the chosen free-tier vendor — BLOCKING_DECISIONS.md
  #1) per symbol, refreshed on the symbol's configured monitoring frequency.
- **FR-12.** Catalyst/earnings evidence: next earnings date (if known) and
  an explicit event-risk classification (FR-24) when it falls inside the
  2–10 day swing horizon.
- **FR-13.** News evidence: recent headlines (source, timestamp, url) —
  MVP shows headlines as raw evidence for the committee to read, not a
  pre-computed sentiment score (that's Phase 2, BLOCKING_DECISIONS.md #1).
- **FR-14.** Every evidence item carries the same provenance envelope as
  `PriceBar` (principle 3): source, symbol, timestamp, timezone, freshness
  status. A missing or stale evidence item is shown as missing/stale, never
  silently backfilled or interpolated (principle 4/5).
- **FR-15.** If a required evidence category is unavailable for a symbol
  (vendor error, rate limit, no data), the committee role that would have
  used it says so explicitly and the CIO's confidence for that
  recommendation is lowered accordingly (principle 5) — never masked.

### Investment committee (FR-16–FR-20)
- **FR-16.** Eight distinct roles run against the same evidence bundle for a
  given symbol: Bull Analyst, Bear Analyst, Technical Analyst, Fundamental
  Analyst, Macro Strategist, Risk Manager, Portfolio Manager, CIO/Judge.
  Each role has its own prompt version and a structured (schema-validated)
  output — never free text alone (docs/MODEL_GOVERNANCE.md).
- **FR-17.** Bull and Bear roles argue their case from the same evidence,
  explicitly required to cite specific evidence items (not just assert a
  view) — auditable back to FR-14's provenance.
- **FR-18.** Risk Manager and Portfolio Manager roles receive the
  deterministic gate outputs (FR-21–FR-26) as tool results, not as
  something they compute themselves — they reason about and narrate the
  numbers, never invent or override them (principle 6/7).
- **FR-19.** CIO/Judge produces the final synthesized recommendation
  **after** every deterministic gate has already run and after every other
  role has responded — the CIO cannot approve something a deterministic
  gate has already blocked (e.g. an earnings-window block, a risk-budget
  breach) — that's a code-enforced ordering, not a prompt instruction.
- **FR-20.** Committee runs are cost-bounded by a versioned, auditable
  pre-filter (BLOCKING_DECISIONS.md #3) — not every symbol gets a full
  committee run every day.

### Deterministic recommendation and risk gates (FR-21–FR-27)
- **FR-21.** Stop/target computation is ATR- and structure-aware: ATR-based
  distance, nearest meaningful support/resistance, gap-risk adjustment
  (recent overnight gap magnitude), catalyst-timing adjustment (tighter or
  no new entry inside an earnings window), and a trailing-stop rule once a
  position is favorably extended.
- **FR-22.** Position size = risk budget (regime-adjusted, FR-02) ÷ stop
  distance, then capped by: total allocation ceiling, single-name liquidity
  (never size beyond a configurable fraction of average daily volume),
  sector concentration, portfolio correlation, and a speculative-name cap
  (smaller max allocation for names flagged speculative,
  BLOCKING_DECISIONS.md #8).
- **FR-23.** No add-on to an existing position is proposed solely because
  price fell. An add-on requires: a new, evidenced catalyst distinct from
  the original thesis, confirmation the original thesis is still intact,
  a defined total risk for the combined position, and full committee
  review — enforced as a hard precondition check, not a prompt suggestion.
- **FR-24.** Any recommendation for a symbol with earnings inside the
  2–10 day holding horizon carries an explicit, user-visible event-risk
  warning — shown before the recommendation action, not buried in prose.
- **FR-25.** The system can and does recommend `NO_ACTION` and holding cash
  — there is no code path that forces a non-cash recommendation when the
  evidence doesn't support one.
- **FR-26.** Every gate's pass/fail and the exact numbers behind it
  (regime-adjusted budget, stop distance, sizing cap that bound, earnings-
  window check) are recorded and shown to the user alongside the
  recommendation (principle 9) — a rejected trade is exactly as
  auditable as an approved one.
- **FR-27.** Recommendation output is one of six values: `BUY`, `SELL`,
  `HOLD`, `WATCH`, `AVOID`, `NO_ACTION` — never a bare numeric score
  presented as the whole answer.

### Premarket plan, intraday alerts, EOD review (FR-28–FR-31)
- **FR-28.** A scheduled premarket job produces one concise, timestamped
  plan artifact per trading day: regime summary, per-Tier-1-name one-line
  status, full committee output for the pre-filtered subset, any
  quarantined-symbol or earnings-window warnings.
- **FR-29.** A scheduled intraday job checks open journal positions against
  the active-trade-monitor rules (FR-32) and any Tier-1 name that crosses a
  configurable alert-worthy threshold (e.g. stop distance closing, a fresh
  catalyst appearing) and posts to an in-app alerts feed
  (BLOCKING_DECISIONS.md #9).
- **FR-30.** A scheduled EOD job summarizes the day: what was recommended,
  what the user actually did (FR-35), and closing regime/portfolio state.
- **FR-31.** Every scheduled artifact (premarket/EOD) is stored and
  retrievable by date — a user reviewing "what did it tell me last
  Tuesday" gets the actual historical artifact, not a re-computed one that
  may differ if evidence changed since.

### Manual trade journal and holdings reconciliation (FR-32–FR-34)
- **FR-32.** A broker-agnostic journal entry: symbol, side, quantity,
  price, timestamp, broker/account label, optional link to the
  recommendation that prompted it, free-text notes.
- **FR-33.** The journal is the primary tracked portfolio
  (BLOCKING_DECISIONS.md #5); the existing Alpaca paper-broker portfolio
  remains available as a separate, clearly-labeled practice sandbox — the
  two are never silently merged into one number.
- **FR-34.** Holdings reconciliation for the journal is user-driven (the
  user attests the journal matches their real broker's position) — there is
  no automated reconciliation against a real external broker in MVP (no
  such integration exists); the existing Alpaca-vs-derived reconciliation
  (shipped MVP) is unchanged and continues to apply only to the practice
  sandbox.

### Active trade monitor (FR-35–FR-36)
- **FR-35.** For every open journal position, a deterministic evaluation
  against the same stop/target/thesis-intact logic (FR-21, FR-23) yields
  one of: `HOLD`, `TIGHTEN_STOP`, `TAKE_PARTIAL`, `EXIT`, `WATCH_CLOSELY` —
  with the specific numbers/evidence behind the suggestion.
- **FR-36.** A monitor suggestion is a suggestion, never an automated
  action — nothing in this capability places, modifies, or cancels an
  order (principle 10/11 apply even though there's no live order path to
  begin with).

### Performance dashboard (FR-37–FR-39)
- **FR-37.** Realized and unrealized P&L, win rate, average win/loss size,
  average R-multiple (P&L ÷ initial risked amount), max drawdown, and a
  benchmark comparison (existing SPY-benchmark pattern from backtesting) —
  computed from the journal (FR-33).
- **FR-38.** Every dashboard number is derived, not stored redundantly
  (same "one shared point-in-time helper" pattern the shipped MVP already
  uses for portfolio snapshots) — dashboard, EOD review, and performance
  views can never disagree with each other about the same fact.
- **FR-39.** Time-windowed views (trailing week/month/all-time) at minimum.

### Recommendation-vs-reality tracking (FR-40–FR-42)
- **FR-40.** Every recommendation is linked (when applicable) to the
  journal entry the user actually made — classified as `FOLLOWED`
  (materially matches: same symbol/side, size and entry within a
  configurable tolerance), `IGNORED` (no linked entry within a configurable
  window), or `MODIFIED` (linked, but size/price/timing meaningfully
  differs) — computed, not self-reported.
- **FR-41.** Once a linked position closes, the actual outcome (P&L,
  R-multiple, whether the stop or target was the actual exit reason) is
  attached to the original recommendation record.
- **FR-42.** This dataset is the explicit, named prerequisite for principle
  15's future calibration work — visible in the performance dashboard as
  "recommendations followed vs. ignored vs. modified" and their outcomes,
  even before calibration itself exists (docs/MVP_PLAN.md's Phase 2).

### Backtesting and walk-forward (FR-43–FR-44)
- **FR-43.** The existing single-window backtest engine (shipped MVP,
  unchanged mechanism) extends to the new deterministic gates (regime-
  adjusted sizing, ATR+structure stops) so a backtest actually reflects
  what the live system would have done, not the old flat-threshold rule.
- **FR-44.** Walk-forward evaluation (rolling/anchored windows) is a named,
  designed-later capability (docs/MVP_PLAN.md's Phase 2) — not built this
  pass, but the existing `BacktestRun` schema is confirmed compatible with
  being called repeatedly across rolling windows without a redesign.

### Controlled learning and governance (FR-45–FR-46)
- **FR-45.** Every configurable threshold introduced by this refinement
  (regime bands, risk-budget %, stop/target parameters, committee
  pre-filter bar, speculative-name volatility percentile) lives in a
  versioned config, gated by the existing propose→backtest→compare→approve
  loop (ADR-026/027/028) — no new governance mechanism, same one, bigger
  config surface.
- **FR-46.** A strategy-version change that touches committee prompts
  (not just numeric thresholds) still requires the same gate — a prompt
  edit is a strategy change like any other (principle 16 doesn't
  distinguish "code threshold" from "prompt text").

### Paper-broker integration (FR-47)
- **FR-47.** Unchanged from the shipped MVP: Alpaca paper broker via the
  existing `PaperBrokerProvider` adapter; no live-order capability exists
  anywhere in the codebase (principle 10).

### Evidence provenance, freshness, observability, privacy, auditability (FR-48–FR-50)
- **FR-48.** Every new entity introduced by this refinement (evidence
  items, committee outputs, journal entries, regime snapshots, scheduled
  artifacts) writes an `AuditEvent` on creation, reusing the existing
  pattern — no new audit mechanism.
- **FR-49.** No new vendor call happens without the freshness/provenance
  envelope (FR-14) attached to its result before it's ever shown to a
  committee role or the user.
- **FR-50.** No PII beyond the single local user's own use exists anywhere
  in the new evidence/journal/committee data — same posture as the shipped
  MVP's docs/SECURITY.md.

## Non-functional requirements

- **NFR-01 (cost boundedness).** Committee LLM spend is bounded by a
  versioned, auditable pre-filter (FR-20) — total daily spend must be
  predictable within the cost estimate in docs/PROVIDER_MATRIX.md, not
  open-ended.
- **NFR-02 (latency).** The premarket plan must be fully generated before
  a reasonable "check it before the bell" reading window — target under 5
  minutes wall-clock for the scheduled job (not a live-request SLA; nobody
  is waiting synchronously for 8×N committee calls).
- **NFR-03 (determinism of numeric truth).** Every number a committee role
  or the CIO narrative references must trace back to a tool result computed
  in plain code — never an LLM-estimated figure (principle 6/7, structurally
  enforced the same way the shipped MVP's `llm_tools.py` allow-list already
  does).
- **NFR-04 (auditability).** Any past recommendation, gate decision, or
  scheduled artifact must be fully reconstructable from stored data alone —
  no dependency on re-querying a live vendor to explain a past decision.
- **NFR-05 (graceful degradation).** A vendor outage/rate-limit for any one
  evidence category degrades that category's contribution (lower
  confidence, explicit "unavailable" marker) — it never blocks the rest of
  the pipeline or crashes the premarket job (principle 5).
- **NFR-06 (operability by one person).** No new infrastructure component
  that a single personal-use deployment can't run and understand — the
  scheduler decision (BLOCKING_DECISIONS.md #4) is the concrete test case
  for this.
- **NFR-07 (test coverage).** Every new deterministic module (regime
  classification, stop/target, position sizing, symbol validation,
  recommendation-vs-reality classification) gets the same fixtures-only,
  no-live-API unit-test treatment as the shipped MVP's `services/` layer
  (docs/TEST_STRATEGY.md, unchanged policy).
- **NFR-08 (privacy).** No new secret is ever exposed client-side; every new
  vendor key lives server-side only, following the existing
  `apps/api/.env` pattern.

## Explicitly out of scope

See docs/MVP_PLAN.md's "Future / explicitly out of scope" section — live
trading, opportunity discovery beyond Tier 1, options/futures/crypto/
non-US markets, multi-user/auth, and a second connected broker are all
unchanged exclusions from the shipped MVP, reaffirmed here rather than
silently dropped from this document.

## User stories

Written as the persona above; each maps to the `FR-*` ids it exercises.

1. *As the user, before market open, I want a short plan that tells me which
   of my 48 names actually deserve a look today, so I don't have to
   individually check 48 charts.* (FR-04, FR-20, FR-28)
2. *As the user, when a name clears the daily bar, I want to see the actual
   bull case, bear case, and what the risk manager and portfolio manager
   think about position size and portfolio fit — not just a number.*
   (FR-16–FR-19)
3. *As the user, when I'm about to enter a name with earnings in 4 days, I
   want that flagged loudly before I read anything else about it.* (FR-24)
4. *As the user, if a name I'm holding has fallen and I'm tempted to add
   more, I want the system to require an actual new reason before it'll
   even consider proposing that — not just let me talk myself into it.*
   (FR-23)
5. *As the user, I want to log a trade I placed at my actual broker in ten
   seconds, and have my dashboard reflect it immediately.* (FR-32, FR-38)
6. *As the user, holding a position that's now up meaningfully, I want to be
   told when it's time to tighten my stop or take a partial, not have to
   remember to check.* (FR-35, FR-29)
7. *As the user, at the end of the month, I want to know not just my P&L but
   whether I actually followed the system's calls, and whether the ones I
   followed were the ones that worked.* (FR-37, FR-40–FR-42)
8. *As the user, if the system wants to change how it scores or sizes
   trades, I want to see a real backtest comparison before I approve
   anything — same as today.* (FR-45, unchanged from shipped MVP)

## Acceptance criteria (measurable)

- **AC-01.** Given the Tier 1 list as specified, running symbol validation
  produces a validation record for all 48 entries, with `SKHY`, `SPCX`,
  `NASA`, and `DRAM` specifically resolved to either `RESOLVED` (with the
  canonical match shown) or `QUARANTINED` (with a specific reason) — never
  silently included as if pre-validated.
- **AC-02.** A `STRESSED` regime classification measurably reduces the
  position-sizing risk budget and/or allocation ceiling versus the same
  inputs under a `CALM` classification — demonstrated with a fixture test,
  not just asserted in prose.
- **AC-03.** A committee run for a symbol with earnings inside the holding
  horizon includes an explicit event-risk warning in its output — a
  fixture test with a known earnings date inside vs. outside the window
  produces different (warning vs. no-warning) output.
- **AC-04.** An add-on proposal for an existing position, with no new
  catalyst evidence supplied, is rejected before it reaches the committee —
  a fixture test asserts the gate fires, not just that the CIO "chose" to
  say no.
- **AC-05.** At least one fixture backtest produces a `NO_ACTION`/cash
  outcome for a period with no qualifying setups — proving the system
  doesn't force an action when there isn't one to recommend.
- **AC-06.** A journal entry logged against a recommendation, within the
  configured tolerance, classifies as `FOLLOWED`; one outside tolerance
  (different size) classifies as `MODIFIED`; one with no linked entry after
  the configured window classifies as `IGNORED` — three fixture tests,
  three distinct outcomes.
- **AC-07.** Every new entity's creation produces exactly one `AuditEvent`
  row — verified for at least one instance of each new entity type
  (evidence item, committee output, journal entry, regime snapshot,
  scheduled artifact).
- **AC-08.** A simulated vendor failure for one evidence category (e.g.
  fundamentals) still produces a complete premarket plan for that symbol,
  with that category marked unavailable and the recommendation's confidence
  measurably lower than an otherwise-identical run with that category
  present.
