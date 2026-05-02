from app.db.model import (
    LearningContentModel,
    MilestoneModel,
    RoadmapModel,
    SkillPathModel,
    UserModel,
)
from app.schema.entities import (
    LearningContentItem,
    MilestoneItem,
    MilestoneWithSkillPaths,
    RoadmapFull,
    SkillPathItem,
)
from app.schema.enums import PracticeMode
from pydantic import TypeAdapter
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# --- Mappers: DB row → Pydantic entity ---


learning_content_adapter = TypeAdapter(LearningContentItem)


def _to_learning_content_item(row: LearningContentModel) -> LearningContentItem:
    return learning_content_adapter.validate_python(row.payload)


def _to_skillpath_item(row: SkillPathModel) -> SkillPathItem:
    return SkillPathItem(
        skillpath_id=row.skillpath_id,
        milestone_id=row.milestone_id,
        title=row.title,
        description=row.description,
        estimated_hours=row.estimated_hours,
        prerequisite_skillpath_ids=row.prerequisite_skillpath_ids or [],
        learning_objectives=row.learning_objectives or [],
        status=row.status,
        need_generation=row.need_generation,
        need_modification=row.need_modification,
        revision_reason=row.revision_reason,
        affected_downstream_ids=row.affected_downstream_ids or [],
        practice_mode=PracticeMode(row.practice_mode) if row.practice_mode else None,
        learning_contents=[
            _to_learning_content_item(content)
            for content in sorted(
                row.learning_contents, key=lambda item: item.order_index
            )
        ],
    )


def _to_milestone_item(row: MilestoneModel) -> MilestoneItem:
    return MilestoneItem(
        roadmap_uuid=row.roadmap_id,
        milestone_id=row.milestone_id,
        title=row.title,
        description=row.description,
        objective=row.objective,
        estimated_hours=row.estimated_hours,
        order_index=row.order_index,
        dependency_titles=row.dependency_titles or [],
        prerequisite_milestone_ids=row.prerequisite_milestone_ids or [],
        status=row.status,
        need_modification=row.need_modification,
        revision_reason=row.revision_reason,
    )


# --- Read ---


async def get_roadmap_full(
    user_id: str, roadmap_id: str, session: AsyncSession
) -> RoadmapFull:
    """Read roadmap from DB and return nested structure for agent consumption."""
    result = await session.execute(
        select(RoadmapModel)
        .where(
            RoadmapModel.roadmap_id == roadmap_id,
            RoadmapModel.user_id == user_id,
        )
        .options(
            selectinload(RoadmapModel.milestones)
            .selectinload(MilestoneModel.skillpaths)
            .selectinload(SkillPathModel.learning_contents)
        )
    )
    roadmap = result.scalar_one_or_none()
    if not roadmap:
        raise ValueError(f"Roadmap {roadmap_id} not found for user {user_id}")

    milestones = []
    for m in sorted(roadmap.milestones, key=lambda x: x.order_index):
        skillpaths = [_to_skillpath_item(sp) for sp in m.skillpaths]
        milestones.append(
            MilestoneWithSkillPaths(
                milestone_id=m.milestone_id,
                roadmap_uuid=m.roadmap_id,
                title=m.title,
                description=m.description,
                objective=m.objective,
                estimated_hours=m.estimated_hours,
                order_index=m.order_index,
                dependency_titles=m.dependency_titles or [],
                prerequisite_milestone_ids=m.prerequisite_milestone_ids or [],
                status=m.status,
                need_modification=m.need_modification,
                revision_reason=m.revision_reason,
                skillpaths=skillpaths,
            )
        )

    return RoadmapFull(
        roadmap_id=roadmap.roadmap_id,
        version=roadmap.version,
        summary=roadmap.summary,
        target_outcome=roadmap.target_outcome,
        assumptions=roadmap.assumptions or [],
        milestones=milestones,
    )


# --- Write: planner saves flat output to DB ---


async def save_roadmap(
    user_id: str,
    roadmap_id: str,
    version: int,
    summary: str,
    target_outcome: str,
    assumptions: list[str],
    milestones: list[MilestoneItem],
    skillpaths: list[SkillPathItem],
    session: AsyncSession,
) -> str:
    """Save full planner output (flat) to DB. Called by run_planner tool."""
    user = await session.get(UserModel, user_id)
    if not user:
        session.add(UserModel(user_id=user_id))

    session.add(
        RoadmapModel(
            user_id=user_id,
            roadmap_id=roadmap_id,
            version=version,
            summary=summary,
            target_outcome=target_outcome,
            assumptions=assumptions,
        )
    )

    for m in milestones:
        session.add(
            MilestoneModel(
                milestone_id=m.milestone_id,
                roadmap_id=roadmap_id,
                title=m.title,
                description=m.description,
                objective=m.objective,
                estimated_hours=m.estimated_hours,
                order_index=m.order_index,
                dependency_titles=m.dependency_titles,
                prerequisite_milestone_ids=m.prerequisite_milestone_ids,
                status=m.status,
                need_modification=m.need_modification,
                revision_reason=m.revision_reason,
            )
        )

    for sp in skillpaths:
        session.add(
            SkillPathModel(
                skillpath_id=sp.skillpath_id,
                milestone_id=sp.milestone_id,
                title=sp.title,
                description=sp.description,
                estimated_hours=sp.estimated_hours,
                prerequisite_skillpath_ids=sp.prerequisite_skillpath_ids,
                learning_objectives=sp.learning_objectives,
                status=sp.status,
                need_generation=sp.need_generation,
                need_modification=sp.need_modification,
                revision_reason=sp.revision_reason,
                affected_downstream_ids=sp.affected_downstream_ids,
                practice_mode=sp.practice_mode.value if sp.practice_mode else None,
            )
        )
        for order_index, content in enumerate(sp.learning_contents):
            session.add(
                LearningContentModel(
                    content_id=content.content_id,
                    skillpath_id=sp.skillpath_id,
                    content_type=content.content_type.value,
                    title=content.title,
                    description=content.description,
                    order_index=order_index,
                    payload=content.model_dump(mode="json"),
                )
            )

    await session.commit()
    return roadmap_id


# --- Write: agent review patches ---


async def update_milestone(
    user_id: str, milestone_id: str, session: AsyncSession, **fields
) -> MilestoneItem:
    """Patch any fields on a milestone. Agent calls this during review."""
    result = await session.execute(
        select(MilestoneModel)
        .join(RoadmapModel, MilestoneModel.roadmap_id == RoadmapModel.roadmap_id)
        .where(
            MilestoneModel.milestone_id == milestone_id,
            RoadmapModel.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"Milestone {milestone_id} not found for user {user_id}")
    for key, value in fields.items():
        setattr(row, key, value)
    await session.commit()
    return _to_milestone_item(row)


async def update_skillpath(
    user_id: str, skillpath_id: str, session: AsyncSession, **fields
) -> SkillPathItem:
    """Patch any fields on a skillpath. Agent calls this during review."""
    result = await session.execute(
        select(SkillPathModel)
        .join(
            MilestoneModel, SkillPathModel.milestone_id == MilestoneModel.milestone_id
        )
        .join(RoadmapModel, MilestoneModel.roadmap_id == RoadmapModel.roadmap_id)
        .where(
            SkillPathModel.skillpath_id == skillpath_id,
            RoadmapModel.user_id == user_id,
        )
        .options(selectinload(SkillPathModel.learning_contents))
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"SkillPath {skillpath_id} not found for user {user_id}")
    for key, value in fields.items():
        setattr(row, key, value)
    await session.commit()
    return _to_skillpath_item(row)


async def save_generated_skillpaths(
    user_id: str, skillpaths: list[SkillPathItem], session: AsyncSession
) -> list[SkillPathItem]:
    """Persist generated learning content for existing skillpaths."""
    skillpath_ids = [sp.skillpath_id for sp in skillpaths]
    if not skillpath_ids:
        return []

    result = await session.execute(
        select(SkillPathModel)
        .join(
            MilestoneModel, SkillPathModel.milestone_id == MilestoneModel.milestone_id
        )
        .join(RoadmapModel, MilestoneModel.roadmap_id == RoadmapModel.roadmap_id)
        .where(
            SkillPathModel.skillpath_id.in_(skillpath_ids),
            RoadmapModel.user_id == user_id,
        )
        .options(selectinload(SkillPathModel.learning_contents))
    )
    rows = {row.skillpath_id: row for row in result.scalars()}
    missing_ids = set(skillpath_ids) - set(rows)
    if missing_ids:
        raise ValueError(
            f"SkillPath {sorted(missing_ids)[0]} not found for user {user_id}"
        )

    await session.execute(
        delete(LearningContentModel).where(
            LearningContentModel.skillpath_id.in_(skillpath_ids)
        )
    )

    for sp in skillpaths:
        row = rows[sp.skillpath_id]
        row.status = sp.status
        row.need_generation = sp.need_generation
        row.practice_mode = sp.practice_mode.value if sp.practice_mode else None
        for order_index, content in enumerate(sp.learning_contents):
            session.add(
                LearningContentModel(
                    content_id=content.content_id,
                    skillpath_id=sp.skillpath_id,
                    content_type=content.content_type.value,
                    title=content.title,
                    description=content.description,
                    order_index=order_index,
                    payload=content.model_dump(mode="json"),
                )
            )

    await session.commit()
    session.expire_all()

    reloaded = await session.execute(
        select(SkillPathModel)
        .where(SkillPathModel.skillpath_id.in_(skillpath_ids))
        .options(selectinload(SkillPathModel.learning_contents))
    )
    reloaded_by_id = {row.skillpath_id: row for row in reloaded.scalars()}
    return [
        _to_skillpath_item(reloaded_by_id[skillpath_id])
        for skillpath_id in skillpath_ids
    ]
