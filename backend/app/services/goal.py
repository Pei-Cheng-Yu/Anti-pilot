from app.db.model import GoalModel, UserModel
from app.schema.entities import GoalSpec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _to_goal_spec(row: GoalModel) -> GoalSpec:
    return GoalSpec(
        title=row.title,
        description=row.description,
        target_outcome=row.target_outcome,
        deadline=row.deadline,
        criteria=row.criteria or [],
        constraints=row.constraints or [],
    )


async def save_goal(user_id: str, goal: GoalSpec, session: AsyncSession) -> GoalSpec:
    """Save or replace a user's goal. Creates user row if not exists."""
    user = await session.get(UserModel, user_id)
    if not user:
        session.add(UserModel(user_id=user_id))

    existing = await session.execute(
        select(GoalModel).where(GoalModel.user_id == user_id)
    )
    row = existing.scalar_one_or_none()

    if row:
        row.title = goal.title
        row.description = goal.description
        row.target_outcome = goal.target_outcome
        row.deadline = goal.deadline
        row.criteria = goal.criteria
        row.constraints = goal.constraints
    else:
        row = GoalModel(
            user_id=user_id,
            title=goal.title,
            description=goal.description,
            target_outcome=goal.target_outcome,
            deadline=goal.deadline,
            criteria=goal.criteria,
            constraints=goal.constraints,
        )
        session.add(row)

    await session.commit()
    return _to_goal_spec(row)


async def get_goal(user_id: str, session: AsyncSession) -> GoalSpec:
    """Fetch a user's goal."""
    result = await session.execute(
        select(GoalModel).where(GoalModel.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"No goal found for user {user_id}")
    return _to_goal_spec(row)
