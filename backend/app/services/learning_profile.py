from app.db.model import LearningProfileModel, UserModel
from app.schema.entities import LearningProfile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _to_learning_profile(row: LearningProfileModel) -> LearningProfile:
    return LearningProfile(
        baseline_level=row.baseline_level,
        prior_knowledges=row.prior_knowledges or [],
        weak_areas=row.weak_areas or [],
        pace_preference=row.pace_preference,
        confidence_level=row.confidence_level,
        needs_recap=row.needs_recap,
        prefers_examples_first=row.prefers_examples_first,
        overload_risk=row.overload_risk,
    )


async def save_learning_profile(
    user_id: str, profile: LearningProfile, session: AsyncSession
) -> LearningProfile:
    """Save or replace a user's learning profile. Creates user row if not exists."""
    user = await session.get(UserModel, user_id)
    if not user:
        session.add(UserModel(user_id=user_id))

    existing = await session.execute(
        select(LearningProfileModel).where(LearningProfileModel.user_id == user_id)
    )
    row = existing.scalar_one_or_none()

    if row:
        row.baseline_level = profile.baseline_level
        row.prior_knowledges = profile.prior_knowledges
        row.weak_areas = profile.weak_areas
        row.pace_preference = profile.pace_preference
        row.confidence_level = profile.confidence_level
        row.needs_recap = profile.needs_recap
        row.prefers_examples_first = profile.prefers_examples_first
        row.overload_risk = profile.overload_risk
    else:
        row = LearningProfileModel(
            user_id=user_id,
            baseline_level=profile.baseline_level,
            prior_knowledges=profile.prior_knowledges,
            weak_areas=profile.weak_areas,
            pace_preference=profile.pace_preference,
            confidence_level=profile.confidence_level,
            needs_recap=profile.needs_recap,
            prefers_examples_first=profile.prefers_examples_first,
            overload_risk=profile.overload_risk,
        )
        session.add(row)

    await session.commit()
    return _to_learning_profile(row)


async def get_learning_profile(user_id: str, session: AsyncSession) -> LearningProfile:
    """Fetch a user's learning profile."""
    result = await session.execute(
        select(LearningProfileModel).where(LearningProfileModel.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"No learning profile found for user {user_id}")
    return _to_learning_profile(row)
