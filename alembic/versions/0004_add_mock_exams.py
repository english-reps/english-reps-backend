"""Add mock_exams table for timed TOEIC Listening and Reading mock exams."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mock_exams",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("section", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("question_ids", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("answers", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("flagged_ids", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("played_keys", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_index", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("remaining_seconds", sa.Integer(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=True),
        sa.Column("scaled_score", sa.Integer(), nullable=True),
        sa.Column("wrong_ids", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("part_stats", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("section IN ('listening', 'reading')"),
        sa.CheckConstraint("status IN ('in_progress', 'completed')"),
        sa.CheckConstraint("current_index >= 0 AND remaining_seconds >= 0 AND duration_seconds > 0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mock_exams_user_id", "mock_exams", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mock_exams_user_id", table_name="mock_exams")
    op.drop_table("mock_exams")
