import asyncio
import os
from datetime import date
from pathlib import Path
from uuid import uuid4

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
from app.langgraph.learning_director import agent as learning_director_agent
from app.schema.entities import (
    ArticleLearningContent,
    CodingProblemLearningContent,
    GoalSpec,
    LearningProfile,
    MultipleChoiceLearningContent,
    MultipleChoiceOption,
)
from app.schema.enums import PracticeMode
from app.services import goal as goal_service
from app.services import learning_profile as learning_profile_service
from app.services import roadmap as roadmap_service
from dotenv import load_dotenv
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Load environment variables so model and DB config behave the same as other tests.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class FakeContentGenerationGraph:
    def invoke(self, state: dict) -> dict:
        generated_skillpaths = []
        for skillpath in state["skillpaths"]:
            article = ArticleLearningContent(
                content_id=f"article-{skillpath.skillpath_id}",
                skillpath_id=skillpath.skillpath_id,
                title=f"{skillpath.title} article",
                description=f"Generated article for {skillpath.title}.",
                skill_intro=f"Why {skillpath.title} matters in this roadmap.",
                reading_content=f"Core explanation for {skillpath.title}.",
            )
            assessment = self._make_assessment(skillpath)
            generated_skillpaths.append(
                skillpath.model_copy(
                    update={
                        "status": "generated",
                        "need_generation": False,
                        "learning_contents": [article, assessment],
                    }
                )
            )

        return {"generated_skillpaths": generated_skillpaths}

    def _make_assessment(self, skillpath):
        if skillpath.practice_mode == PracticeMode.CODING_PROBLEM:
            return CodingProblemLearningContent(
                content_id=f"coding-{skillpath.skillpath_id}",
                skillpath_id=skillpath.skillpath_id,
                title=f"{skillpath.title} practice",
                description=f"Generated coding practice for {skillpath.title}.",
                prompt=f"Implement a small exercise for {skillpath.title}.",
                difficulty="easy",
                starter_code=None,
                expected_output=None,
                hints=["Start with the smallest working case."],
            )

        return MultipleChoiceLearningContent(
            content_id=f"quiz-{skillpath.skillpath_id}",
            skillpath_id=skillpath.skillpath_id,
            title=f"{skillpath.title} check",
            description=f"Generated concept check for {skillpath.title}.",
            question=f"What is the key idea in {skillpath.title}?",
            options=[
                MultipleChoiceOption(option_id="A", text="A distractor"),
                MultipleChoiceOption(option_id="B", text="The core concept"),
                MultipleChoiceOption(option_id="C", text="Another distractor"),
            ],
            correct_option_id="B",
            explanation="B matches the generated skillpath objective.",
        )


def make_goal() -> GoalSpec:
    return GoalSpec(
        title="Learn FastAPI Backend Development",
        description="Learn FastAPI from beginner to building a CRUD backend project.",
        target_outcome="Build a production-style FastAPI backend with auth and database support.",
        deadline=date(2026, 6, 30),
        criteria=[
            "Understand HTTP and REST fundamentals",
            "Build CRUD APIs with validation",
            "Use async database access cleanly",
        ],
        constraints=[
            "6 hours per week",
            "Prefer hands-on learning",
            "Need examples before theory",
        ],
    )


def make_profile() -> LearningProfile:
    return LearningProfile(
        baseline_level="intermediate",
        prior_knowledges=["Python basics", "C++", "C#"],
        weak_areas=["HTTP concepts", "database design", "async programming"],
        pace_preference="balanced",
        confidence_level="medium",
        needs_recap=False,
        prefers_examples_first=True,
        overload_risk="medium",
    )


def extract_final_text(result: dict) -> str:
    messages = result.get("messages", [])
    for message in reversed(messages):
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "").strip()
                    if text:
                        parts.append(text)
            if parts:
                return "\n".join(parts)
    return "<no assistant text found>"


async def cleanup_user(session_factory: async_sessionmaker, user_id: str) -> None:
    async with session_factory() as session:
        roadmap_ids = list(
            (
                await session.execute(
                    select(RoadmapModel.roadmap_id).where(
                        RoadmapModel.user_id == user_id
                    )
                )
            ).scalars()
        )
        if roadmap_ids:
            milestone_ids = list(
                (
                    await session.execute(
                        select(MilestoneModel.milestone_id).where(
                            MilestoneModel.roadmap_id.in_(roadmap_ids)
                        )
                    )
                ).scalars()
            )
            if milestone_ids:
                skillpath_ids = list(
                    (
                        await session.execute(
                            select(SkillPathModel.skillpath_id).where(
                                SkillPathModel.milestone_id.in_(milestone_ids)
                            )
                        )
                    ).scalars()
                )
                if skillpath_ids:
                    await session.execute(
                        delete(LearningContentModel).where(
                            LearningContentModel.skillpath_id.in_(skillpath_ids)
                        )
                    )
                await session.execute(
                    delete(SkillPathModel).where(
                        SkillPathModel.milestone_id.in_(milestone_ids)
                    )
                )
            await session.execute(
                delete(MilestoneModel).where(MilestoneModel.roadmap_id.in_(roadmap_ids))
            )
        await session.execute(
            delete(RoadmapModel).where(RoadmapModel.user_id == user_id)
        )
        await session.execute(
            delete(LearningProfileModel).where(LearningProfileModel.user_id == user_id)
        )
        await session.execute(delete(GoalModel).where(GoalModel.user_id == user_id))
        await session.execute(delete(UserModel).where(UserModel.user_id == user_id))
        await session.commit()


async def main() -> None:
    user_id = f"learning-director-smoke-{uuid4()}"
    goal_id = f"goal-{uuid4()}"
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    use_real_content_graph = os.getenv("LEARNING_DIRECTOR_SMOKE_REAL_CONTENT") == "1"

    print("Starting learning director smoke test")
    print("Make sure the MCP server is running at http://localhost:8001/mcp")
    print(f"Using fake user_id: {user_id}")
    print(f"Using fake goal_id: {goal_id}")
    if use_real_content_graph:
        print("Using real content graph and real ADK content generator.")
    else:
        print(
            "Using fake content graph for deterministic content-generation persistence."
        )

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            await goal_service.save_goal(user_id, make_goal(), session, goal_id=goal_id)
            await learning_profile_service.save_learning_profile(
                user_id, make_profile(), session
            )

        if not use_real_content_graph:
            learning_director_agent._content_generator = FakeContentGenerationGraph()
        agent = await learning_director_agent.create_learning_director()
        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"CURRENT_USER_ID: {user_id}\n"
                            f"CURRENT_GOAL_ID: {goal_id}\n\n"
                            "My learning goal and learning profile are already saved in the system. "
                            "Please load the saved goal with this goal_id and load my learning profile "
                            "with this user_id using your tools. Then create my learning roadmap, review it, "
                            "fix any real issues, generate learning content for every skillpath, "
                            "save that content to the database, and tell me when it is ready."
                        ),
                    }
                ]
            },
            context={"user_id": user_id, "goal_id": goal_id},
            config={
                "configurable": {
                    "thread_id": f"thread-{user_id}",
                    "user_id": user_id,
                    "goal_id": goal_id,
                }
            },
        )

        print("\n=== FINAL AGENT MESSAGE ===")
        print(extract_final_text(result))

        async with session_factory() as session:
            roadmap_ids = list(
                (
                    await session.execute(
                        select(RoadmapModel.roadmap_id).where(
                            RoadmapModel.user_id == user_id
                        )
                    )
                ).scalars()
            )
            if not roadmap_ids:
                raise AssertionError("No roadmap was created for the smoke-test user.")

            latest_roadmap_id = roadmap_ids[-1]
            roadmap = await roadmap_service.get_roadmap_full(
                user_id, latest_roadmap_id, session
            )

        total_skillpaths = sum(len(m.skillpaths) for m in roadmap.milestones)
        total_hours = sum(m.estimated_hours for m in roadmap.milestones)
        skillpaths_with_content = sum(
            1
            for milestone in roadmap.milestones
            for skillpath in milestone.skillpaths
            if skillpath.learning_contents
        )
        total_learning_contents = sum(
            len(skillpath.learning_contents)
            for milestone in roadmap.milestones
            for skillpath in milestone.skillpaths
        )

        if total_skillpaths == 0:
            raise AssertionError("Roadmap was created without skillpaths.")
        if skillpaths_with_content != total_skillpaths:
            raise AssertionError(
                "Learning director did not generate and persist content for every skillpath. "
                f"Expected {total_skillpaths}, got {skillpaths_with_content}."
            )

        print("\n=== ROADMAP CHECK ===")
        print(f"roadmap_id: {roadmap.roadmap_id}")
        print(f"milestones: {len(roadmap.milestones)}")
        print(f"skillpaths: {total_skillpaths}")
        print(f"milestone_hours: {total_hours}")
        print(f"skillpaths_with_content: {skillpaths_with_content}")
        print(f"learning_content_items: {total_learning_contents}")
        print(
            "Smoke test passed: roadmap and generated learning content were persisted."
        )
    finally:
        await cleanup_user(session_factory, user_id)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
