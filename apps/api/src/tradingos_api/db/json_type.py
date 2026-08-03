import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# Native JSONB on Postgres (production); portable JSON everywhere else
# (in-memory SQLite in endpoint-test fixtures) — SQLAlchemy's standard
# cross-dialect JSON pattern. Shared by every model with a JSON column.
PORTABLE_JSON = sa.JSON().with_variant(JSONB(), "postgresql")
