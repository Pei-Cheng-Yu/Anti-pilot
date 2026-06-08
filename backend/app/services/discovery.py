from app.db.model import DiscoveryConversationModel, GoalModel, UserModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def save_discovery_conversation(
    user_id: str,
    conversation_id: str,
    session: AsyncSession,
    goal_id: str | None = None,
) -> DiscoveryConversationModel:
    """Persist a Discovery Agent conversation owner mapping."""
    user = await session.get(UserModel, user_id)
    if not user:
        session.add(UserModel(user_id=user_id))
    if goal_id is not None:
        await _ensure_goal_owned_by_user(user_id, goal_id, session)

    row = DiscoveryConversationModel(
        conversation_id=conversation_id,
        user_id=user_id,
        goal_id=goal_id,
    )
    session.add(row)
    await session.commit()
    return row


async def get_discovery_conversation_user_id(
    conversation_id: str, session: AsyncSession
) -> str:
    """Return the user_id that owns a discovery conversation."""
    row = await session.get(DiscoveryConversationModel, conversation_id)
    if not row:
        raise ValueError(f"Discovery conversation {conversation_id} not found")
    return row.user_id


async def get_discovery_conversation_context(
    conversation_id: str, session: AsyncSession
) -> tuple[str, str | None]:
    """Return the user_id and optional goal_id for a Discovery conversation."""
    row = await session.get(DiscoveryConversationModel, conversation_id)
    if not row:
        raise ValueError(f"Discovery conversation {conversation_id} not found")
    return row.user_id, row.goal_id


async def bind_discovery_conversation_goal(
    conversation_id: str,
    user_id: str,
    goal_id: str,
    session: AsyncSession,
) -> DiscoveryConversationModel:
    """Bind an existing Discovery conversation to a goal owned by the user."""
    row = await session.get(DiscoveryConversationModel, conversation_id)
    if not row or row.user_id != user_id:
        raise ValueError(f"Discovery conversation {conversation_id} not found")
    await _ensure_goal_owned_by_user(user_id, goal_id, session)
    row.goal_id = goal_id
    await session.commit()
    return row


async def _ensure_goal_owned_by_user(
    user_id: str, goal_id: str, session: AsyncSession
) -> None:
    result = await session.execute(
        select(GoalModel).where(
            GoalModel.user_id == user_id,
            GoalModel.goal_id == goal_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise ValueError(f"Goal {goal_id} not found for user {user_id}")
