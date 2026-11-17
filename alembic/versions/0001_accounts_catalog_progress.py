"""Accounts, seeded catalog and per-user idempotent practice progress."""

import json
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    data = Path(__file__).resolve().parent.parent / "data"
    for statement in (data / "schema-v1.sql").read_text().split(";"):
        if statement.strip():
            op.execute(sa.text(statement))
    catalog = sa.table(
        "catalog_items",
        sa.column("id", sa.String),
        sa.column("category", sa.String),
        sa.column("content", JSONB),
    )
    op.bulk_insert(catalog, json.loads((data / "catalog-v1.json").read_text()))


def downgrade():
    for table in [
        "auth_attempts",
        "progress_imports",
        "study_events",
        "progress",
        "sessions",
        "catalog_items",
        "users",
    ]:
        op.drop_table(table)
