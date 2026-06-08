from app.db.model import MilestoneModel, RoadmapModel, SkillPathModel
from app.schema.entities import (
    MilestoneCustomizationRequest,
    MilestoneCustomizationResponse,
)
from app.services import roadmap as roadmap_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def customize_milestone(
    *,
    user_id: str,
    roadmap_id: str,
    milestone_id: str,
    request: MilestoneCustomizationRequest,
    session: AsyncSession,
) -> MilestoneCustomizationResponse:
    """Apply a narrow milestone customization through service-owned validation."""
    await _ensure_milestone_owned_by_user(user_id, roadmap_id, milestone_id, session)
    fields = _milestone_update_fields(request)
    if not fields:
        return MilestoneCustomizationResponse(
            applied=False,
            message="What would you like to change about this milestone?",
            follow_up_required=True,
        )

    milestone = await roadmap_service.update_milestone(
        user_id,
        milestone_id,
        session,
        **fields,
    )
    affected_skillpath_ids: list[str] = []
    if request.mark_skillpaths_for_regeneration:
        affected_skillpath_ids = await _mark_milestone_skillpaths_for_regeneration(
            user_id,
            roadmap_id,
            milestone_id,
            session,
        )

    return MilestoneCustomizationResponse(
        applied=True,
        message="Milestone updated.",
        milestone=milestone,
        affected_skillpath_ids=affected_skillpath_ids,
        follow_up_required=False,
    )


def _milestone_update_fields(request: MilestoneCustomizationRequest) -> dict:
    has_concrete_update = any(
        value is not None
        for value in (
            request.title,
            request.description,
            request.objective,
            request.estimated_hours,
        )
    )
    if not has_concrete_update:
        return {}

    return {
        key: value
        for key, value in {
            "title": request.title,
            "description": request.description,
            "objective": request.objective,
            "estimated_hours": request.estimated_hours,
            "need_modification": True,
            "revision_reason": request.instructions.strip() or None,
        }.items()
        if value is not None
    }


async def _ensure_milestone_owned_by_user(
    user_id: str,
    roadmap_id: str,
    milestone_id: str,
    session: AsyncSession,
) -> None:
    result = await session.execute(
        select(MilestoneModel)
        .join(RoadmapModel, MilestoneModel.roadmap_id == RoadmapModel.roadmap_id)
        .where(
            RoadmapModel.user_id == user_id,
            RoadmapModel.roadmap_id == roadmap_id,
            MilestoneModel.milestone_id == milestone_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise ValueError(f"Milestone {milestone_id} not found for user {user_id}")


async def _mark_milestone_skillpaths_for_regeneration(
    user_id: str,
    roadmap_id: str,
    milestone_id: str,
    session: AsyncSession,
) -> list[str]:
    result = await session.execute(
        select(SkillPathModel)
        .join(
            MilestoneModel, SkillPathModel.milestone_id == MilestoneModel.milestone_id
        )
        .join(RoadmapModel, MilestoneModel.roadmap_id == RoadmapModel.roadmap_id)
        .where(
            RoadmapModel.user_id == user_id,
            RoadmapModel.roadmap_id == roadmap_id,
            MilestoneModel.milestone_id == milestone_id,
        )
    )
    rows = list(result.scalars())
    for row in rows:
        row.need_modification = True
        row.need_generation = True
        row.revision_reason = row.revision_reason or "Milestone was customized."
    await session.commit()
    return [row.skillpath_id for row in rows]
