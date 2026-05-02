from datetime import date
from uuid import uuid4

import pytest
from app.core.config import settings
from app.db.model import (
    Base,
    GoalModel,
    LearningContentModel,
    LearningProfileModel,
    MilestoneModel,
    RoadmapModel,
    SkillPathModel,
    UserModel,
)
from app.schema.entities import (
    ArticleLearningContent,
    GoalSpec,
    LearningProfile,
    MilestoneItem,
    SkillPathItem,
    SourceLink,
)
from app.schema.enums import LearningContentType, PracticeMode
from app.services import goal as goal_service
from app.services import learning_profile as learning_profile_service
from app.services import roadmap as roadmap_service
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def make_goal() -> GoalSpec:
    return GoalSpec(
        title="Learn FastAPI",
        description="Build REST APIs with FastAPI from scratch.",
        target_outcome="Build a production-style FastAPI project.",
        deadline=date(2026, 6, 30),
        criteria=["Can build CRUD endpoints", "Understands validation"],
        constraints=["6 hours per week"],
    )


def make_profile() -> LearningProfile:
    return LearningProfile(
        baseline_level="intermediate",
        prior_knowledges=["Python basics"],
        weak_areas=["async programming"],
        pace_preference="balanced",
        confidence_level="medium",
        needs_recap=False,
        prefers_examples_first=True,
        overload_risk="low",
    )


def make_milestone(roadmap_id: str) -> MilestoneItem:
    return MilestoneItem(
        roadmap_uuid=roadmap_id,
        milestone_id=f"m-{uuid4().hex[:8]}",
        title="Foundations",
        description="Core concepts",
        objective="Understand HTTP and Python async",
        estimated_hours=10.0,
        order_index=1,
        status="ready",
    )


def make_skillpath(milestone_id: str) -> SkillPathItem:
    return SkillPathItem(
        skillpath_id=f"sp-{uuid4().hex[:8]}",
        milestone_id=milestone_id,
        title="HTTP Basics",
        description="Learn HTTP fundamentals",
        estimated_hours=3.0,
        status="ready",
        need_generation=True,
        need_modification=False,
        practice_mode=None,
    )


def make_article_content(skillpath_id: str) -> ArticleLearningContent:
    return ArticleLearningContent(
        content_id=f"content-{uuid4().hex[:8]}",
        skillpath_id=skillpath_id,
        title="HTTP request basics",
        description="A short article introducing HTTP requests.",
        skill_intro="HTTP is the shared language between clients and APIs.",
        reading_content="A request has a method, URL, headers, and optional body.",
        references=[
            SourceLink(
                title="MDN HTTP overview",
                url="https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview",
            )
        ],
    )


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


@pytest.fixture
async def test_user():
    user_id = f"itest-{uuid4()}"
    try:
        yield user_id
    finally:
        engine = create_async_engine(
            settings.database_url,
            poolclass=NullPool,
        )
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as cleanup_session:
            roadmap_ids = list(
                (
                    await cleanup_session.execute(
                        select(RoadmapModel.roadmap_id).where(
                            RoadmapModel.user_id == user_id
                        )
                    )
                ).scalars()
            )
            if roadmap_ids:
                milestone_ids = list(
                    (
                        await cleanup_session.execute(
                            select(MilestoneModel.milestone_id).where(
                                MilestoneModel.roadmap_id.in_(roadmap_ids)
                            )
                        )
                    ).scalars()
                )
                if milestone_ids:
                    skillpath_ids = list(
                        (
                            await cleanup_session.execute(
                                select(SkillPathModel.skillpath_id).where(
                                    SkillPathModel.milestone_id.in_(milestone_ids)
                                )
                            )
                        ).scalars()
                    )
                    if skillpath_ids:
                        await cleanup_session.execute(
                            delete(LearningContentModel).where(
                                LearningContentModel.skillpath_id.in_(skillpath_ids)
                            )
                        )
                    await cleanup_session.execute(
                        delete(SkillPathModel).where(
                            SkillPathModel.milestone_id.in_(milestone_ids)
                        )
                    )
                await cleanup_session.execute(
                    delete(MilestoneModel).where(
                        MilestoneModel.roadmap_id.in_(roadmap_ids)
                    )
                )
            await cleanup_session.execute(
                delete(RoadmapModel).where(RoadmapModel.user_id == user_id)
            )
            await cleanup_session.execute(
                delete(LearningProfileModel).where(
                    LearningProfileModel.user_id == user_id
                )
            )
            await cleanup_session.execute(
                delete(GoalModel).where(GoalModel.user_id == user_id)
            )
            await cleanup_session.execute(
                delete(UserModel).where(UserModel.user_id == user_id)
            )
            await cleanup_session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_goal_service_roundtrip(db_session, test_user: str):
    goal = make_goal()

    saved = await goal_service.save_goal(test_user, goal, db_session)
    loaded = await goal_service.get_goal(test_user, db_session)

    assert saved == goal
    assert loaded == goal


@pytest.mark.asyncio
async def test_learning_profile_service_roundtrip(db_session, test_user: str):
    profile = make_profile()

    saved = await learning_profile_service.save_learning_profile(
        test_user, profile, db_session
    )
    loaded = await learning_profile_service.get_learning_profile(test_user, db_session)

    assert saved == profile
    assert loaded == profile


@pytest.mark.asyncio
async def test_roadmap_service_roundtrip_and_scoping(db_session, test_user: str):
    roadmap_id = f"roadmap-{uuid4()}"
    milestone = make_milestone(roadmap_id)
    skillpath = make_skillpath(milestone.milestone_id)

    saved_roadmap_id = await roadmap_service.save_roadmap(
        user_id=test_user,
        roadmap_id=roadmap_id,
        version=1,
        summary="FastAPI learning roadmap",
        target_outcome="Build a production-style FastAPI project.",
        assumptions=["6 hours per week"],
        milestones=[milestone],
        skillpaths=[skillpath],
        session=db_session,
    )
    loaded = await roadmap_service.get_roadmap_full(test_user, roadmap_id, db_session)

    assert saved_roadmap_id == roadmap_id
    assert loaded.roadmap_id == roadmap_id
    assert loaded.summary == "FastAPI learning roadmap"
    assert len(loaded.milestones) == 1
    assert loaded.milestones[0].title == "Foundations"
    assert len(loaded.milestones[0].skillpaths) == 1
    assert loaded.milestones[0].skillpaths[0].title == "HTTP Basics"

    updated_milestone = await roadmap_service.update_milestone(
        test_user,
        milestone.milestone_id,
        db_session,
        objective="Understand HTTP, routing, and async patterns in Python",
    )
    updated_skillpath = await roadmap_service.update_skillpath(
        test_user,
        skillpath.skillpath_id,
        db_session,
        estimated_hours=2.0,
        practice_mode=PracticeMode.CODING_PROBLEM.value,
    )
    reloaded = await roadmap_service.get_roadmap_full(test_user, roadmap_id, db_session)

    assert "async patterns" in updated_milestone.objective
    assert updated_skillpath.estimated_hours == 2.0
    assert updated_skillpath.practice_mode == PracticeMode.CODING_PROBLEM
    assert "async patterns" in reloaded.milestones[0].objective
    assert reloaded.milestones[0].skillpaths[0].estimated_hours == 2.0
    assert (
        reloaded.milestones[0].skillpaths[0].practice_mode
        == PracticeMode.CODING_PROBLEM
    )

    with pytest.raises(ValueError, match="not found for user"):
        await roadmap_service.get_roadmap_full("other-user", roadmap_id, db_session)


@pytest.mark.asyncio
async def test_roadmap_service_persists_generated_learning_contents(
    db_session, test_user: str
):
    roadmap_id = f"roadmap-{uuid4()}"
    milestone = make_milestone(roadmap_id)
    skillpath = make_skillpath(milestone.milestone_id)

    await roadmap_service.save_roadmap(
        user_id=test_user,
        roadmap_id=roadmap_id,
        version=1,
        summary="FastAPI learning roadmap",
        target_outcome="Build a production-style FastAPI project.",
        assumptions=[],
        milestones=[milestone],
        skillpaths=[skillpath],
        session=db_session,
    )

    generated_skillpath = skillpath.model_copy(
        update={
            "status": "generated",
            "need_generation": False,
            "learning_contents": [make_article_content(skillpath.skillpath_id)],
        }
    )

    saved_skillpaths = await roadmap_service.save_generated_skillpaths(
        test_user, [generated_skillpath], db_session
    )
    loaded = await roadmap_service.get_roadmap_full(test_user, roadmap_id, db_session)
    loaded_skillpath = loaded.milestones[0].skillpaths[0]

    assert saved_skillpaths[0].need_generation is False
    assert loaded_skillpath.status == "generated"
    assert loaded_skillpath.need_generation is False
    assert len(loaded_skillpath.learning_contents) == 1
    assert (
        loaded_skillpath.learning_contents[0].content_type
        == LearningContentType.ARTICLE
    )
    assert loaded_skillpath.learning_contents[0].title == "HTTP request basics"
