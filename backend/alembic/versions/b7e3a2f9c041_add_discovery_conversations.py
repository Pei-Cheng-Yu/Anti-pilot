"""add discovery conversations

Revision ID: b7e3a2f9c041
Revises: 9ad924787a9c
Create Date: 2026-06-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e3a2f9c041"
down_revision: Union[str, Sequence[str], None] = "9ad924787a9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "discovery_conversations",
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_discovery_conversations_user_id_users"),
        ),
        sa.PrimaryKeyConstraint(
            "conversation_id", name=op.f("pk_discovery_conversations")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("discovery_conversations")
