"""add learning contents

Revision ID: 9a7f1d3c2b6e
Revises: c4d952e2efa2
Create Date: 2026-05-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9a7f1d3c2b6e"
down_revision: Union[str, Sequence[str], None] = "c4d952e2efa2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "learning_contents",
        sa.Column("content_id", sa.String(), nullable=False),
        sa.Column("skillpath_id", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["skillpath_id"],
            ["skillpaths.skillpath_id"],
            name=op.f("fk_learning_contents_skillpath_id_skillpaths"),
        ),
        sa.PrimaryKeyConstraint("content_id", name=op.f("pk_learning_contents")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("learning_contents")
