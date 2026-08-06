"""Policy scaffolding for the "TradingOS v2 Decision and Execution
Amendment" (PROJECT_INSTRUCTIONS.md). These modules are deliberately
standalone, pure-Python validation logic — no SQLAlchemy models, no
migration, no router, no provider call. They exist so the four-tier
order-authority taxonomy and the investment/tactical recommendation-mode
separation the amendment requires are enforceable and testable *now*,
ahead of the real features (morning plan generation, the earnings
strategy engine, live broker integration) that will eventually consume
them in a future, separately-approved phase.
"""

from __future__ import annotations
