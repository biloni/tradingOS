"""Demo script for Revision Prompt 13 — event-driven backtesting and
walk-forward validation.

Demonstrates:
1. The locked baseline scenario (2026-02-03 to 2026-07-31, score>=5,
   expected move>=4%) reproduced against a deterministic synthetic
   universe, compared honestly against the prompt's own stated targets
   — and again over the full 2-year synthetic window, since the locked
   window alone is too sparse a sample.
2. All 8 required strategy variants run end-to-end.
3. The score-threshold sensitivity sweep (4-7).
4. Three-window walk-forward evaluation (TRAIN/VALIDATION/OUT_OF_SAMPLE).
5. Persisting one run and reading it back via the drill-down/download
   API path.
6. The assembled go/no-go report and its recommendation.

Run with: `python -m tradingos_api.scripts.demo_prompt13`
"""

from __future__ import annotations

from tradingos_api.db.session import SessionLocal
from tradingos_api.models.enums import EventBacktestStrategyKey
from tradingos_api.services.backtest_engine import BacktestRunConfig, run_backtest
from tradingos_api.services.backtest_persistence import (
    get_backtest_run,
    list_backtest_trades,
    save_backtest_run,
)
from tradingos_api.services.backtest_validation import (
    build_go_no_go_report,
    reproduce_baseline_scenario,
    run_score_threshold_sweep,
    run_walk_forward,
)


def main() -> None:
    db = SessionLocal()
    try:
        print("=== 1. Baseline reproduction: locked scenario vs. widened window ===")
        baseline = reproduce_baseline_scenario(db)
        locked = baseline.locked_window_result
        wide = baseline.wide_window_result
        print(f"  targets: {baseline.targets}")
        print(
            f"  locked window ({locked.config.start} to {locked.config.end}): "
            f"trades={len(locked.trades)}, total_return_pct={locked.total_return_pct}, "
            f"win_rate_pct={locked.trade_stats.win_rate_pct}"
        )
        print(
            f"  wide window ({wide.config.start} to {wide.config.end}): "
            f"trades={len(wide.trades)}, total_return_pct={wide.total_return_pct}, "
            f"win_rate_pct={wide.trade_stats.win_rate_pct}, "
            f"profit_factor={wide.trade_stats.profit_factor}, "
            f"max_drawdown_pct={wide.drawdown.max_drawdown_pct}"
        )
        print(f"  deviation explanation: {baseline.deviation_explanation[:200]}...")

        print("\n=== 2. All 8 required strategy variants ===")
        for key in EventBacktestStrategyKey:
            config = BacktestRunConfig(
                strategy_key=key,
                start=wide.config.start,
                end=wide.config.end,
                universe_start=wide.config.universe_start,
                universe_end=wide.config.universe_end,
            )
            result = run_backtest(db, config)
            print(
                f"  {key.value:32s} trades={len(result.trades):4d} "
                f"total_return_pct={result.total_return_pct}"
            )

        print("\n=== 3. Score-threshold sensitivity (4-7) ===")
        sweep = run_score_threshold_sweep(db)
        for point in sweep:
            print(
                f"  {point.label:6s} trades={point.result.trade_stats.num_trades:4d} "
                f"win_rate_pct={point.result.trade_stats.win_rate_pct}"
            )

        print("\n=== 4. Walk-forward: TRAIN / VALIDATION / OUT_OF_SAMPLE ===")
        for window in run_walk_forward(db):
            print(
                f"  {window.label:14s} ({window.start} to {window.end}) "
                f"trades={len(window.result.trades):4d} "
                f"total_return_pct={window.result.total_return_pct}"
            )

        print("\n=== 5. Persist one run and read it back (drill-down path) ===")
        saved_run = save_backtest_run(db, wide, is_golden_regression=True)
        db.commit()
        reloaded = get_backtest_run(db, saved_run.id)
        assert reloaded is not None
        trades = list_backtest_trades(db, saved_run.id)
        print(f"  persisted run id: {saved_run.id}")
        print(f"  reloaded strategy_key: {reloaded.strategy_key.value}")
        print(f"  reloaded trade count: {len(trades)}")
        print(
            f"  reloaded results_summary.win_rate_pct: "
            f"{reloaded.results_summary.get('win_rate_pct')}"
        )

        print("\n=== 6. Go/no-go report ===")
        report = build_go_no_go_report(db)
        print(f"  strategies compared: {len(report.strategy_comparison)}")
        print(f"  semiconductor-concentration subset trades: "
              f"{len(report.semiconductor_concentration.trades)}")
        print(f"  by-year groups: {[p.label for p in report.by_year]}")
        print(f"  by-sector groups: {[p.label for p in report.by_sector]}")
        print(f"  caveats: {len(report.bias_and_quality_caveats)} recorded")
        print(f"  recommendation: {report.recommendation}")

        print("\nAll Prompt 13 demo state persisted (one EventBacktestRun row).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
