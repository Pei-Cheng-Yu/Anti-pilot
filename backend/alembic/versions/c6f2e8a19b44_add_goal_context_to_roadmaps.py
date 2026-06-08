"""add goal context to roadmaps

Revision ID: c6f2e8a19b44
Revises: b7e3a2f9c041
Create Date: 2026-06-09 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6f2e8a19b44"
down_revision: Union[str, Sequence[str], None] = "b7e3a2f9c041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("goals", sa.Column("goal_id", sa.String(), nullable=True))
    op.execute("UPDATE goals SET goal_id = 'goal-' || id WHERE goal_id IS NULL")
    op.alter_column("goals", "goal_id", nullable=False)
    op.drop_constraint(op.f("uq_goals_user_id"), "goals", type_="unique")
    op.create_unique_constraint(op.f("uq_goals_goal_id"), "goals", ["goal_id"])

    op.add_column("roadmaps", sa.Column("goal_id", sa.String(), nullable=True))
    op.create_foreign_key(
        op.f("fk_roadmaps_goal_id_goals"),
        "roadmaps",
        "goals",
        ["goal_id"],
        ["goal_id"],
    )
    op.execute(
        """
        UPDATE roadmaps
        SET goal_id = goals.goal_id
        FROM goals
        WHERE roadmaps.user_id = goals.user_id
          AND (
            SELECT count(*)
            FROM goals AS user_goals
            WHERE user_goals.user_id = roadmaps.user_id
          ) = 1
        """
    )
    op.create_unique_constraint(op.f("uq_roadmaps_goal_id"), "roadmaps", ["goal_id"])

    op.add_column(
        "discovery_conversations", sa.Column("goal_id", sa.String(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_discovery_conversations_goal_id_goals"),
        "discovery_conversations",
        "goals",
        ["goal_id"],
        ["goal_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_discovery_conversations_goal_id_goals"),
        "discovery_conversations",
        type_="foreignkey",
    )
    op.drop_column("discovery_conversations", "goal_id")

    op.drop_constraint(op.f("uq_roadmaps_goal_id"), "roadmaps", type_="unique")
    op.drop_constraint(
        op.f("fk_roadmaps_goal_id_goals"), "roadmaps", type_="foreignkey"
    )
    op.drop_column("roadmaps", "goal_id")

    op.drop_constraint(op.f("uq_goals_goal_id"), "goals", type_="unique")
    op.create_unique_constraint(op.f("uq_goals_user_id"), "goals", ["user_id"])
    op.drop_column("goals", "goal_id")
