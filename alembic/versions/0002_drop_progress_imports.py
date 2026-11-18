"""Drop unused legacy browser progress import table."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("progress_imports")


def downgrade() -> None:
    op.create_table(
        "progress_imports",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("import_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "import_id"),
    )
