from datetime import date
from uuid import uuid4

import pytest
from app.core.config import settings
from app.db.model import (
    Base,
    DiscoveryConversationModel,
    GoalModel,
    LearningContentModel,
    LearningProfileModel,
    MilestoneModel,
    ReviewConceptModel,
    RoadmapModel,
    SkillPathModel,
    UserModel,
)
from app.schema.entities import (
    ArticleLearningContent,
    GoalSpec,
    LearningProfile,
    MilestoneCustomizationRequest,
    MilestoneItem,
    SkillPathItem,
    SourceLink,
)
from app.schema.enums import LearningContentType, PracticeMode
from app.services import discovery as discovery_service
from app.services import goal as goal_service
from app.services import learning_profile as learning_profile_service
from app.services import roadmap as roadmap_service
from app.services import roadmap_customization as roadmap_customization_service
from sqlalchemy import delete, func, select
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
                        content_ids = list(
                            (
                                await cleanup_session.execute(
                                    select(LearningContentModel.content_id).where(
                                        LearningContentModel.skillpath_id.in_(
                                            skillpath_ids
                                        )
                                    )
                                )
                            ).scalars()
                        )
                        if content_ids:
                            await cleanup_session.execute(
                                delete(ReviewConceptModel).where(
                                    ReviewConceptModel.source_ref_id.in_(content_ids)
                                )
                            )
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
                delete(DiscoveryConversationModel).where(
                    DiscoveryConversationModel.user_id == user_id
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
async def test_goal_service_supports_multiple_goals_for_one_user(
    db_session, test_user: str
):
    first_goal_id = f"goal-fastapi-{uuid4()}"
    second_goal_id = f"goal-sqlalchemy-{uuid4()}"
    first_goal = make_goal()
    second_goal = make_goal().model_copy(
        update={
            "title": "Learn SQLAlchemy",
            "description": "Build reliable async persistence with SQLAlchemy.",
            "target_outcome": "Ship async database-backed API routes.",
        }
    )

    saved_first = await goal_service.save_goal(
        test_user, first_goal, db_session, goal_id=first_goal_id
    )
    saved_second = await goal_service.save_goal(
        test_user, second_goal, db_session, goal_id=second_goal_id
    )
    loaded_first = await goal_service.get_goal(
        test_user, db_session, goal_id=first_goal_id
    )
    loaded_second = await goal_service.get_goal(
        test_user, db_session, goal_id=second_goal_id
    )
    rows = list(
        (
            await db_session.execute(
                select(GoalModel).where(GoalModel.user_id == test_user)
            )
        ).scalars()
    )

    assert saved_first == first_goal
    assert saved_second == second_goal
    assert loaded_first == first_goal
    assert loaded_second == second_goal
    assert {row.goal_id for row in rows} == {first_goal_id, second_goal_id}


@pytest.mark.asyncio
async def test_goal_service_rejects_cross_user_goal_access(db_session, test_user: str):
    goal = make_goal()
    goal_id = f"goal-private-{uuid4()}"

    await goal_service.save_goal(test_user, goal, db_session, goal_id=goal_id)

    with pytest.raises(ValueError, match="No goal found"):
        await goal_service.get_goal(
            "other-user",
            db_session,
            goal_id=goal_id,
        )


@pytest.mark.asyncio
async def test_discovery_conversation_can_bind_goal_after_creation(
    db_session, test_user: str
):
    goal_id = f"goal-fastapi-{uuid4()}"
    conversation_id = f"convo-{uuid4()}"
    await goal_service.save_goal(test_user, make_goal(), db_session, goal_id=goal_id)
    await discovery_service.save_discovery_conversation(
        test_user, conversation_id, db_session
    )

    before_user_id, before_goal_id = (
        await discovery_service.get_discovery_conversation_context(
            conversation_id, db_session
        )
    )
    await discovery_service.bind_discovery_conversation_goal(
        conversation_id, test_user, goal_id, db_session
    )
    after_user_id, after_goal_id = (
        await discovery_service.get_discovery_conversation_context(
            conversation_id, db_session
        )
    )
    row = await db_session.get(DiscoveryConversationModel, conversation_id)

    assert before_user_id == test_user
    assert before_goal_id is None
    assert after_user_id == test_user
    assert after_goal_id == goal_id
    assert row.goal_id == goal_id


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
        title="FastAPI",
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
    assert loaded.title == "FastAPI"
    assert loaded.summary == "FastAPI learning roadmap"
    assert len(loaded.milestones) == 1
    assert loaded.milestones[0].title == "Foundations"
    assert len(loaded.milestones[0].skillpaths) == 1
    assert loaded.milestones[0].skillpaths[0].roadmap_id == roadmap_id
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
async def test_add_skillpath_creates_new_skillpath_under_milestone(
    db_session, test_user: str
):
    roadmap_id = f"roadmap-{uuid4()}"
    milestone = make_milestone(roadmap_id)
    await roadmap_service.save_roadmap(
        user_id=test_user,
        roadmap_id=roadmap_id,
        title="FastAPI",
        version=1,
        summary="s",
        target_outcome="o",
        assumptions=[],
        milestones=[milestone],
        skillpaths=[make_skillpath(milestone.milestone_id)],
        session=db_session,
    )

    created = await roadmap_service.add_skillpath(
        user_id=test_user,
        milestone_id=milestone.milestone_id,
        title="Unit testing",
        description="Write pytest unit tests",
        session=db_session,
    )

    # Server-generated id, flagged for content generation, no content yet.
    assert created.skillpath_id.startswith("sp-")
    assert created.title == "Unit testing"
    assert created.milestone_id == milestone.milestone_id
    assert created.roadmap_id == roadmap_id
    assert created.need_generation is True
    assert created.learning_contents == []

    reloaded = await roadmap_service.get_roadmap_full(test_user, roadmap_id, db_session)
    sp_ids = {sp.skillpath_id for sp in reloaded.milestones[0].skillpaths}
    assert created.skillpath_id in sp_ids
    assert len(reloaded.milestones[0].skillpaths) == 2

    # Unknown milestone / cross-user is rejected.
    with pytest.raises(ValueError, match="not found for user"):
        await roadmap_service.add_skillpath(
            user_id="other-user",
            milestone_id=milestone.milestone_id,
            title="x",
            description="y",
            session=db_session,
        )


@pytest.mark.asyncio
async def test_roadmap_service_links_one_primary_roadmap_per_goal(
    db_session, test_user: str
):
    first_goal_id = f"goal-fastapi-{uuid4()}"
    second_goal_id = f"goal-sqlalchemy-{uuid4()}"
    first_goal = make_goal()
    second_goal = make_goal().model_copy(update={"title": "Learn SQLAlchemy"})
    await goal_service.save_goal(
        test_user, first_goal, db_session, goal_id=first_goal_id
    )
    await goal_service.save_goal(
        test_user, second_goal, db_session, goal_id=second_goal_id
    )

    first_roadmap_id = f"roadmap-{uuid4()}"
    first_milestone = make_milestone(first_roadmap_id)
    await roadmap_service.save_roadmap(
        user_id=test_user,
        goal_id=first_goal_id,
        roadmap_id=first_roadmap_id,
        version=1,
        summary="FastAPI roadmap",
        target_outcome=first_goal.target_outcome,
        assumptions=[],
        milestones=[first_milestone],
        skillpaths=[make_skillpath(first_milestone.milestone_id)],
        session=db_session,
    )

    second_roadmap_id = f"roadmap-{uuid4()}"
    second_milestone = make_milestone(second_roadmap_id)
    await roadmap_service.save_roadmap(
        user_id=test_user,
        goal_id=second_goal_id,
        roadmap_id=second_roadmap_id,
        version=1,
        summary="SQLAlchemy roadmap",
        target_outcome=second_goal.target_outcome,
        assumptions=[],
        milestones=[second_milestone],
        skillpaths=[make_skillpath(second_milestone.milestone_id)],
        session=db_session,
    )

    loaded_first = await roadmap_service.get_roadmap_full(
        test_user, first_roadmap_id, db_session
    )
    loaded_second = await roadmap_service.get_roadmap_full(
        test_user, second_roadmap_id, db_session
    )

    assert loaded_first.summary == "FastAPI roadmap"
    assert loaded_second.summary == "SQLAlchemy roadmap"

    duplicate_roadmap_id = f"roadmap-{uuid4()}"
    duplicate_milestone = make_milestone(duplicate_roadmap_id)
    with pytest.raises(ValueError, match="already exists for goal"):
        await roadmap_service.save_roadmap(
            user_id=test_user,
            goal_id=first_goal_id,
            roadmap_id=duplicate_roadmap_id,
            version=1,
            summary="Duplicate FastAPI roadmap",
            target_outcome=first_goal.target_outcome,
            assumptions=[],
            milestones=[duplicate_milestone],
            skillpaths=[make_skillpath(duplicate_milestone.milestone_id)],
            session=db_session,
        )


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
    original_generated_content_id = generated_skillpath.learning_contents[0].content_id

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
    first_content_id = loaded_skillpath.learning_contents[0].content_id
    assert (
        generated_skillpath.learning_contents[0].content_id
        == original_generated_content_id
    )
    assert first_content_id != original_generated_content_id

    review_result = await db_session.execute(
        select(ReviewConceptModel).where(
            ReviewConceptModel.user_id == test_user,
            ReviewConceptModel.source_type == "skill_path",
            ReviewConceptModel.source_ref_id
            == loaded_skillpath.learning_contents[0].content_id,
        )
    )
    review_card = review_result.scalar_one_or_none()
    assert review_card is not None
    assert review_card.concept_metadata["skillpath_id"] == skillpath.skillpath_id
    assert review_card.concept_metadata["content_type"] == "article"
    review_card.reps = 3
    review_card.lapses = 1
    review_card.stability = 4.0
    review_card.difficulty = 5.0
    await db_session.commit()

    await roadmap_service.save_generated_skillpaths(
        test_user, [generated_skillpath], db_session
    )
    reloaded = await roadmap_service.get_roadmap_full(test_user, roadmap_id, db_session)
    reloaded_content_id = (
        reloaded.milestones[0].skillpaths[0].learning_contents[0].content_id
    )
    assert reloaded_content_id == first_content_id
    preserved_review_result = await db_session.execute(
        select(ReviewConceptModel).where(
            ReviewConceptModel.user_id == test_user,
            ReviewConceptModel.source_type == "skill_path",
            ReviewConceptModel.source_ref_id == first_content_id,
        )
    )
    preserved_review_card = preserved_review_result.scalar_one()
    assert preserved_review_card.reps == 3
    assert preserved_review_card.lapses == 1

    review_count_result = await db_session.execute(
        select(func.count())
        .select_from(ReviewConceptModel)
        .where(
            ReviewConceptModel.user_id == test_user,
            ReviewConceptModel.source_type == "skill_path",
            ReviewConceptModel.source_ref_id == first_content_id,
        )
    )
    assert review_count_result.scalar_one() == 1

    changed_content = make_article_content(skillpath.skillpath_id).model_copy(
        update={"reading_content": "A changed explanation for regenerated content."}
    )
    changed_skillpath = skillpath.model_copy(
        update={
            "status": "generated",
            "need_generation": False,
            "learning_contents": [changed_content],
        }
    )
    await roadmap_service.save_generated_skillpaths(
        test_user, [changed_skillpath], db_session
    )
    reset_review_result = await db_session.execute(
        select(ReviewConceptModel).where(
            ReviewConceptModel.user_id == test_user,
            ReviewConceptModel.source_type == "skill_path",
            ReviewConceptModel.source_ref_id == first_content_id,
        )
    )
    reset_review_card = reset_review_result.scalar_one()
    assert reset_review_card.reps == 0
    assert reset_review_card.lapses == 0


@pytest.mark.asyncio
async def test_customize_milestone_updates_fields_and_marks_skillpaths(
    db_session, test_user: str
):
    goal_id = f"goal-fastapi-{uuid4()}"
    await goal_service.save_goal(test_user, make_goal(), db_session, goal_id=goal_id)
    roadmap_id = f"roadmap-{uuid4()}"
    milestone = make_milestone(roadmap_id)
    skillpath = make_skillpath(milestone.milestone_id)
    await roadmap_service.save_roadmap(
        user_id=test_user,
        goal_id=goal_id,
        roadmap_id=roadmap_id,
        version=1,
        summary="FastAPI roadmap",
        target_outcome="Build FastAPI APIs",
        assumptions=[],
        milestones=[milestone],
        skillpaths=[skillpath],
        session=db_session,
    )

    result = await roadmap_customization_service.customize_milestone(
        user_id=test_user,
        roadmap_id=roadmap_id,
        milestone_id=milestone.milestone_id,
        request=MilestoneCustomizationRequest(
            instructions="Slow this milestone down and add async dependency injection emphasis.",
            objective="Understand async routing and dependency injection.",
            estimated_hours=12.0,
        ),
        session=db_session,
    )
    reloaded = await roadmap_service.get_roadmap_full(test_user, roadmap_id, db_session)

    assert result.applied is True
    assert result.follow_up_required is False
    assert result.milestone is not None
    assert "dependency injection" in result.milestone.objective
    assert result.affected_skillpath_ids == [skillpath.skillpath_id]
    assert reloaded.milestones[0].skillpaths[0].need_modification is True
    assert reloaded.milestones[0].skillpaths[0].need_generation is True


@pytest.mark.asyncio
async def test_customize_milestone_returns_followup_for_ambiguous_request(
    db_session, test_user: str
):
    goal_id = f"goal-fastapi-{uuid4()}"
    await goal_service.save_goal(test_user, make_goal(), db_session, goal_id=goal_id)
    roadmap_id = f"roadmap-{uuid4()}"
    milestone = make_milestone(roadmap_id)
    await roadmap_service.save_roadmap(
        user_id=test_user,
        goal_id=goal_id,
        roadmap_id=roadmap_id,
        version=1,
        summary="FastAPI roadmap",
        target_outcome="Build FastAPI APIs",
        assumptions=[],
        milestones=[milestone],
        skillpaths=[],
        session=db_session,
    )

    result = await roadmap_customization_service.customize_milestone(
        user_id=test_user,
        roadmap_id=roadmap_id,
        milestone_id=milestone.milestone_id,
        request=MilestoneCustomizationRequest(instructions="Please improve it."),
        session=db_session,
    )

    assert result.applied is False
    assert result.follow_up_required is True
    assert result.message


@pytest.mark.asyncio
async def test_customize_milestone_rejects_cross_user_access(
    db_session, test_user: str
):
    goal_id = f"goal-fastapi-{uuid4()}"
    await goal_service.save_goal(test_user, make_goal(), db_session, goal_id=goal_id)
    roadmap_id = f"roadmap-{uuid4()}"
    milestone = make_milestone(roadmap_id)
    await roadmap_service.save_roadmap(
        user_id=test_user,
        goal_id=goal_id,
        roadmap_id=roadmap_id,
        version=1,
        summary="FastAPI roadmap",
        target_outcome="Build FastAPI APIs",
        assumptions=[],
        milestones=[milestone],
        skillpaths=[],
        session=db_session,
    )

    with pytest.raises(ValueError, match="not found for user"):
        await roadmap_customization_service.customize_milestone(
            user_id="other-user",
            roadmap_id=roadmap_id,
            milestone_id=milestone.milestone_id,
            request=MilestoneCustomizationRequest(objective="Change it"),
            session=db_session,
        )
