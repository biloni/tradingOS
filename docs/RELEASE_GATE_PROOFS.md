# Release-Gate Proofs (Revision Prompt 16)

Four specific properties this paper-beta release needs to actually hold,
each proven against real code and a real test run (not asserted from
memory) — dated **2026-08-11**, against commit history through the
release-gate journey tests (task: release-gate tests). Feeds directly
into task: final gate check + tag paper beta below.

Where a proof turned up a genuine gap rather than confirming the
property held, it's recorded as a gap here, honestly, not smoothed
over — that is the actual value of doing this pass.

## 1. Provenance — every order traces back to what caused it

**Claim:** a submitted paper order can always be traced back to the
recommendation, evidence, and human decision that produced it.

**Proof.** The full chain is a strict foreign-key path, every link
written by the same transaction that advances state, never
back-filled:

```
RecommendationVersion (deterministic_inputs_snapshot, score, rationale)
  -> OrderProposal.recommendation_version_id
  -> OrderProposalVersion (quantity/price/rationale at proposal time)
  -> ApprovalBoundFields.recommendation_version_id (re-stamped, not re-derived)
       + integrity_hash = compute_bound_fields_hash(...)  (services/order_authority.py)
  -> BrokerSubmissionAttempt.order_approval_id, .resulting_order_id
  -> Order -> Execution
```

`ApprovalBoundFields` is an **immutable snapshot** taken once at
approval time (`routers/order_authority.py::create_order_approval()`)
— `integrity_hash` changes if any bound field (quantity, price, side,
attached legs, `recommendation_version_id`) changes, which
`tests/test_services_order_authority.py::TestApprovalHashChangesWithBoundFields`
proves for every field individually. A later `/submit` call re-reads
these bound fields rather than trusting anything the submit request
itself supplies (`OrderSubmitRequest` never carries price/quantity —
see that schema's own docstring: "Bracket prices are never taken from
this request... already bound into `ApprovalBoundFields`... at approval
time").

**Verified end-to-end**: `tests/test_release_gate_journeys.py::TestSyntheticGoldenJourney`
drives the real chain over HTTP — propose (from the seeded AMD
recommendation) → evaluate → approve → submit → fetches the resulting
`Order` and asserts its instrument matches the recommendation's
(`AMD`). This is the first test in this ~700-test suite to exercise
that full chain over HTTP (`test_step_up_reauth.py`'s own docstring
had flagged the missing factory as a known gap; closed by this pass).

## 2. Risk/invalidation — a proposed order can't slip past a risk gate

**Claim:** every risk-relevant condition (stale/missing data, kill
switch, ambiguous broker environment, price moved since approval, an
approval that's expired or already decided) is checked again
immediately before submission, not just once at approval time, and
fails closed.

**Proof, by mechanism:**

- **Hard vetoes** (`services/order_execution.py::refresh_and_recalculate()`
  → `HardVetoInputs`/`evaluate_hard_vetoes()`): stale/missing quote,
  active kill switch, and a non-`PAPER_ALPACA` broker environment each
  independently set `requires_reapproval=True`. A veto never raises —
  it produces `invalidated=True` in the response and flips the
  approval to `INVALIDATED` with an `ApprovalInvalidation` row
  recording why (`ApprovalInvalidationReason.PRICE_MOVED` for price
  moves; the kill-switch/stale-data vetoes reuse the same path). Proven
  live: `tests/test_release_gate_journeys.py::TestFailureJourneys::test_kill_switch_blocks_submission_after_every_earlier_gate_passed`
  — activates the kill switch *after* a real approval already reached
  `APPROVED`, then submits, and asserts `invalidated=True`,
  `order_id=None`, and the approval is now `INVALIDATED`.
- **Wall-clock expiry**: `services/order_authority.py::assert_can_transition_to_approved()`
  re-checks `expires_at` at `/approve` time (a `PENDING` approval whose
  expiry already passed can never reach `APPROVED` even if nothing has
  swept it to `EXPIRED` yet), and `services/order_execution.py::submit_paper_order()`
  re-checks it *again* independently at submit time rather than
  trusting an earlier `APPROVED` read. Proven live:
  `TestFailureJourneys::test_an_already_expired_approval_cannot_be_approved`
  (a `-5`-second `expires_in_seconds` approval is refused at `/approve`
  with a 400 naming "expired," at the router layer — not just the
  already-unit-tested service function,
  `tests/test_services_order_authority.py::TestExpiredApprovalCannotReturnToApproved`).
- **Reject forecloses submission permanently**: once `REJECTED`, no
  path leads back to `APPROVED` (`ORDER_APPROVAL_TRANSITIONS`), so a
  rejected approval can never later be submitted. Proven live:
  `TestFailureJourneys::test_a_rejected_approval_cannot_later_be_submitted`
  — a real `403` naming the `REJECTED` status.
- **Broker-boundary paper-only enforcement (OA-6)**:
  `assert_broker_boundary_is_paper()` runs before anything else inside
  `submit_paper_order()`, independently of account type, environment
  label, and broker base URL — this is what makes "never live" true
  structurally, not by convention (`services/order_execution.py`'s own
  docstring: "Never live... hardcodes `is_live=False`").

**Gap found, not fixed here (flagged for a dedicated follow-up):** the
operator-configured baseline mode (`Settings.operating_mode` —
`RESEARCH_ONLY` by default, unset in this environment's `.env`) is
**only enforced by the frontend choosing a matching `requested_mode`**,
never cross-checked server-side. `services/order_authority.py::compute_effective_mode()`
— whose own docstring says it's "what every order-authority check must
actually gate against" — is called in exactly one place in the whole
`src/` tree: `routers/settings.py::get_operating_mode()`, a read-only
reporting endpoint. Neither `evaluate_order_proposal_policy()` nor
`submit_order_approval()` calls it. Confirmed concretely: this
environment's effective mode is `RESEARCH_ONLY` (no `OPERATING_MODE`
env var set, and the kill switch defaults off), yet
`test_release_gate_journeys.py`'s golden journey successfully submits
a real order with `requested_mode: "PAPER_MANUAL_APPROVAL"` — the
server never questions it. The kill switch itself *is* independently,
correctly enforced (previous bullet) — this gap is specifically about
the baseline mode, not the emergency stop. Practical risk is low today
(single-user personal app; the only real caller is this app's own
frontend, which does try to pick a matching mode) but this undermines
the "four visibly distinct order-authority modes" as an actual
enforced boundary rather than a UI convention. A follow-up task has
been filed to wire `compute_effective_mode()` into both live
enforcement points.

## 3. Audit trail — nothing about an order's history is silently mutated or lost

**Claim:** every state transition, decision, and override is captured
in an append-only record; nothing overwrites or deletes a prior fact.

**Proof:**

- **`AuditEvent`** (`models/audit_event.py`) — `record_type`/`ref_id`/`snapshot`/`created_at`,
  written by `services/audit.py::record_audit_event()`, explicitly
  documented as append-only ("nothing here is ever updated or
  deleted").
- **`BrokerSubmissionAttempt`** — one row per submission *attempt*, not
  per order; a denied/invalidated attempt and a later successful retry
  both persist as separate rows (`_next_attempt_number()`,
  `services/order_execution.py`), so a submission history is never
  overwritten by a subsequent try.
- **`ApprovalInvalidation`** — a dedicated table for *why* an approval
  was invalidated (`reason`, `detail`, `invalidated_at`), separate from
  the approval row's own mutable `status` field, so the reason survives
  independently of whatever the approval's current status later
  becomes.
- **Idempotency-key dedup, closing a real gap this same Revision Prompt
  found** (task: idempotency gaps + scheduled reconciliation): a
  repeated `confirm`/`cancel`/`reconcile` call now correctly 400s or
  replays instead of silently double-applying — `db.get(..., with_for_update=True)`
  closes the *concurrent*-replay race the pre-existing sequential-replay
  check didn't cover (`tests/test_idempotency_review.py`).
- **Structured, redacted logging** (task: structured logging + log
  redaction): every request gets a `request_id` correlating its log
  lines; secret values and field-name-matched sensitive fields are
  redacted by a `logging.Filter` before anything reaches a log sink —
  proven in `core/logging.py`'s own test coverage, not just asserted.
- **`GET /api/v1/ops/job-runs`** and **`GET /api/v1/ops/scheduler`**
  (tasks: job dashboard + metrics; real always-on scheduler) give an
  operator a live, queryable view of what actually ran and when,
  distinguishing a human-triggered run (`triggered_by="manual"`/`"AD_HOC"`)
  from a scheduler-triggered one (`triggered_by="scheduler"`) — the
  provenance chain in §1 extends to *when and by what* a run happened,
  not just what it produced.

No gap found in this section — every mutation path checked writes an
append-only record rather than overwriting a prior fact.

## 4. Morning-plan deadline — the 05:45/06:10 schedule is real, not aspirational

**Claim:** the morning plan actually gets generated on time, retries
correctly if it fails mid-run, and this is no longer purely a
documentation promise ("something has to call this" — the prior state
through task: real always-on scheduler/worker process).

**Proof:**

- **The decision function is correct and fully tested independent of
  any timer**: `services/morning_plan_scheduler.py::decide_schedule()`
  is a pure function of `now_utc` — `tests/test_morning_plan_scheduler.py`
  proves the 05:45 `PRELIMINARY`/06:10 `FINAL` windows, weekend/holiday
  skip, duplicate/rerun protection (a second call in the same window
  doesn't re-fire), and the `STUCK_RUN_TIMEOUT` (15 min) retry-after-crash
  path — a `RUNNING` row older than that is treated as abandoned and
  retried with an incremented attempt number, proven via
  `test_scheduler.py::TestRunDueMorningPlanForUser::test_second_tick_in_the_same_window_does_not_duplicate`
  and the dedicated worker-restart test in `test_morning_plan_scheduler.py`.
- **A real timer now calls it**: `core/scheduler.py`'s in-process
  APScheduler ticks every 60 seconds, calling `decide_schedule()` for
  every user and running generation itself
  (`services/scheduler_jobs.py::run_due_morning_plan_for_user()`) —
  this is the concrete answer to "something has to call this
  repeatedly," previously true only as a documented intention. Verified
  running (`tests/test_scheduler.py::TestSchedulerLifecycle`) and
  status-observable (`GET /api/v1/ops/scheduler`,
  `/ready`'s `scheduler`/`worker` checks — `ok` when actually ticking,
  `not_running` otherwise, never faked).
- **Honest about what "real" still means here**: this is a *local*
  always-on process, not a *deployed* one —
  `morning_plan_scheduler.LOCAL_MODE_WARNING` is unchanged and still
  literally true: the schedule only fires while this machine is awake
  and the process hasn't been stopped. `core/scheduler.py`'s own
  docstring says so explicitly. Turning "local always-on" into "truly
  deployed always-on" is task: Dockerfiles + docker-compose + deployment
  docs's job (containers exist; actual hosting doesn't yet), not this
  one's.

No gap found beyond the already-documented, already-honest local-vs-deployed
distinction — the schedule's own logic is fully proven and now has a
real (if local) timer driving it.

## Summary for the final gate

| Property | Status |
|---|---|
| Provenance | Holds — proven end-to-end, no gap found |
| Risk/invalidation | Holds for kill switch, expiry, rejection, broker-boundary paper-only. **One gap found**: baseline `operating_mode` not server-enforced (follow-up filed, not yet fixed) |
| Audit trail | Holds — no gap found |
| Morning-plan deadline | Holds locally; deployed-always-on is a separate, already-tracked task |

The operating-mode gap is a judgment call for whoever runs task: final
gate check + tag paper beta — fix it first, or tag with it as a known,
documented, low-practical-risk limitation (single-user app, only
caller is this app's own frontend). This document doesn't decide that;
it makes sure the decision is made knowingly.
