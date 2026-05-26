"""add review concepts

Revision ID: d8f3c1a7b4e2
Revises: 9a7f1d3c2b6e
Create Date: 2026-05-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8f3c1a7b4e2"
down_revision: Union[str, Sequence[str], None] = "9a7f1d3c2b6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "review_concepts",
        sa.Column("concept_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_ref_id", sa.String(), nullable=False),
        sa.Column("concept_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.Integer(), nullable=False),
        sa.Column("due", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stability", sa.Float(), nullable=False),
        sa.Column("difficulty", sa.Float(), nullable=False),
        sa.Column("elapsed_days", sa.Integer(), nullable=False),
        sa.Column("scheduled_days", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("concept_id", name=op.f("pk_review_concepts")),
    )
    op.create_index(
        op.f("ix_review_concepts_user_id"),
        "review_concepts",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_review_concepts_user_id"), table_name="review_concepts")
    op.drop_table("review_concepts")
