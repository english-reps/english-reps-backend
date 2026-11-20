"""Drop catalog_items table now that catalog is served from repository JSON files."""

import json
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("progress_entry_id_fkey", "progress", type_="foreignkey")
    op.drop_constraint("study_events_entry_id_fkey", "study_events", type_="foreignkey")
    op.drop_index("ix_catalog_items_category", table_name="catalog_items")
    op.drop_table("catalog_items")


def downgrade() -> None:
    op.create_table(
        "catalog_items",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("content", JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("category IN ('vocabulary', 'listening')"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_items_category", "catalog_items", ["category"], unique=False)
    data = Path(__file__).resolve().parent.parent / "data"
    catalog = sa.table(
        "catalog_items",
        sa.column("id", sa.String),
        sa.column("category", sa.String),
        sa.column("content", JSONB),
    )
    op.bulk_insert(catalog, json.loads((data / "catalog-v1.json").read_text(encoding="utf-8")))
    op.create_foreign_key(
        "progress_entry_id_fkey", "progress", "catalog_items", ["entry_id"], ["id"]
    )
    op.create_foreign_key(
        "study_events_entry_id_fkey", "study_events", "catalog_items", ["entry_id"], ["id"]
    )
