"""merge roadmap and memory heads

Revision ID: 9ad924787a9c
Revises: e21b7c9f4a10, f2b7c9d8e1a4
Create Date: 2026-06-02 21:19:26.979568

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "9ad924787a9c"
down_revision: Union[str, Sequence[str], None] = ("e21b7c9f4a10", "f2b7c9d8e1a4")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
