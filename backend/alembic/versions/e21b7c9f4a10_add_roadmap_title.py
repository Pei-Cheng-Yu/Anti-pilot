"""add roadmap title

Revision ID: e21b7c9f4a10
Revises: d8f3c1a7b4e2
Create Date: 2026-05-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e21b7c9f4a10"
down_revision: Union[str, Sequence[str], None] = "d8f3c1a7b4e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "roadmaps",
        sa.Column(
            "title",
            sa.String(),
            nullable=False,
            server_default="Untitled Roadmap",
        ),
    )
    op.alter_column("roadmaps", "title", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("roadmaps", "title")
