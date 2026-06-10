"""Tests for planner memory injection.

Pure-logic tests (reducer, prompt formatting) are isolated. The linked-mastery
bridge test is DB-backed. Node tests use a fake memory service to avoid live LLM.
"""

from app.langgraph.planner.schema.state import _merge_contexts


def test_merge_contexts_combines_disjoint_keys():
    left = {"m1": "ctx1"}
    right = {"m2": "ctx2"}
    merged = _merge_contexts(left, right)
    assert merged == {"m1": "ctx1", "m2": "ctx2"}


def test_merge_contexts_handles_none_operands():
    assert _merge_contexts(None, {"m1": "ctx1"}) == {"m1": "ctx1"}
    assert _merge_contexts({"m1": "ctx1"}, None) == {"m1": "ctx1"}
    assert _merge_contexts(None, None) == {}


def test_merge_contexts_right_wins_on_key_collision():
    merged = _merge_contexts({"m1": "old"}, {"m1": "new"})
    assert merged == {"m1": "new"}


# ----------------------------------------------------------------------------
# Group 3: linked SkillMasteryState bridge
# ----------------------------------------------------------------------------

from datetime import UTC, datetime  # noqa: E402
from uuid import uuid4  # noqa: E402

import pytest  # noqa: E402
from app.schema.entities import LearnerMemoryNote, LearningMemoryContext  # noqa: E402
from app.schema.enums import MemoryStatus, MemoryType  # noqa: E402


def _note(memory_id, linked_skillpath_ids):
    return LearnerMemoryNote(
        memory_id=memory_id,
        user_id="u-1",
        memory_type=MemoryType.ERROR_PATTERN,
        title="t",
        summary="s",
        linked_skillpath_ids=linked_skillpath_ids,
        status=MemoryStatus.ACTIVE,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


def test_learning_memory_context_has_linked_mastery_states_default():
    ctx = LearningMemoryContext()
    assert ctx.linked_mastery_states == {}


def test_collect_linked_skillpath_ids_dedupes_across_buckets():
    from app.services.learning_memory import _collect_linked_skillpath_ids

    ctx = LearningMemoryContext(
        active_error_patterns=[_note("n1", ["sp-a", "sp-b"])],
        mastery_signals=[_note("n2", ["sp-b"])],
        relevant_notes=[_note("n3", ["sp-c"]), _note("n1", ["sp-a", "sp-b"])],
    )
    assert _collect_linked_skillpath_ids(ctx) == {"sp-a", "sp-b", "sp-c"}


def test_collect_linked_skillpath_ids_empty_when_no_links():
    from app.services.learning_memory import _collect_linked_skillpath_ids

    ctx = LearningMemoryContext(relevant_notes=[_note("n1", [])])
    assert _collect_linked_skillpath_ids(ctx) == set()


# --- DB-backed loader test ---

from app.core.config import settings  # noqa: E402
from app.db.model import (  # noqa: E402
    Base,
    MilestoneModel,
    RoadmapModel,
    SkillMasteryStateModel,
    SkillPathModel,
    UserModel,
)
from app.schema.enums import MasteryStatus  # noqa: E402
from sqlalchemy import delete  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
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
async def seeded_two_skillpaths(db_session):
    user_id = f"planner-itest-{uuid4()}"
    roadmap_id = f"roadmap-{uuid4()}"
    milestone_id = f"milestone-{uuid4()}"
    sp_a = f"sp-a-{uuid4()}"
    sp_b = f"sp-b-{uuid4()}"
    db_session.add(UserModel(user_id=user_id))
    db_session.add(
        RoadmapModel(
            roadmap_id=roadmap_id,
            user_id=user_id,
            version=1,
            summary="s",
            target_outcome="o",
            assumptions=[],
        )
    )
    db_session.add(
        MilestoneModel(
            milestone_id=milestone_id,
            roadmap_id=roadmap_id,
            title="m",
            description="d",
            objective="o",
            estimated_hours=2.0,
            order_index=1,
            dependency_titles=[],
            prerequisite_milestone_ids=[],
            status="generated",
            need_modification=False,
            revision_reason=None,
        )
    )
    for sp in (sp_a, sp_b):
        db_session.add(
            SkillPathModel(
                skillpath_id=sp,
                milestone_id=milestone_id,
                title=sp,
                description="d",
                estimated_hours=1.0,
                prerequisite_skillpath_ids=[],
                learning_objectives=[],
                status="generated",
                need_generation=False,
                need_modification=False,
                revision_reason=None,
                affected_downstream_ids=[],
                practice_mode=None,
            )
        )
    db_session.add(
        SkillMasteryStateModel(
            user_id=user_id,
            skillpath_id=sp_a,
            status=MasteryStatus.MASTERED.value,
            mastery_score=0.9,
            successful_attempts=3,
            failed_attempts=0,
            strong_concepts=["x"],
            weak_concepts=[],
            last_updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await db_session.commit()
    try:
        yield user_id, sp_a, sp_b
    finally:
        await db_session.execute(
            delete(SkillMasteryStateModel).where(
                SkillMasteryStateModel.user_id == user_id
            )
        )
        await db_session.execute(
            delete(SkillPathModel).where(SkillPathModel.milestone_id == milestone_id)
        )
        await db_session.execute(
            delete(MilestoneModel).where(MilestoneModel.milestone_id == milestone_id)
        )
        await db_session.execute(
            delete(RoadmapModel).where(RoadmapModel.roadmap_id == roadmap_id)
        )
        await db_session.execute(delete(UserModel).where(UserModel.user_id == user_id))
        await db_session.commit()


@pytest.mark.asyncio
async def test_load_mastery_states_for_skillpaths(seeded_two_skillpaths, db_session):
    from app.services.learning_memory import load_mastery_states_for_skillpaths

    user_id, sp_a, sp_b = seeded_two_skillpaths
    result = await load_mastery_states_for_skillpaths(user_id, {sp_a, sp_b}, db_session)
    assert set(result.keys()) == {sp_a}  # only sp_a has a mastery state
    assert result[sp_a].status is MasteryStatus.MASTERED


@pytest.mark.asyncio
async def test_load_mastery_states_empty_input_returns_empty(db_session):
    from app.services.learning_memory import load_mastery_states_for_skillpaths

    result = await load_mastery_states_for_skillpaths("u-x", set(), db_session)
    assert result == {}


# ----------------------------------------------------------------------------
# Groups 4-8: nodes (formatter, goal retrieval, prompt injection, worker)
# ----------------------------------------------------------------------------

from datetime import date  # noqa: E402

from app.schema.entities import GoalSpec, LearningProfile, MilestoneItem  # noqa: E402


def _goal(title="Learn async", description="async/await", target_outcome="ship"):
    return GoalSpec(
        title=title,
        description=description,
        target_outcome=target_outcome,
        deadline=date(2026, 12, 31),
        criteria=[],
        constraints=[],
    )


def _profile():
    return LearningProfile(
        baseline_level="beginner",
        prior_knowledges=[],
        weak_areas=[],
        pace_preference="balanced",
        confidence_level="medium",
        needs_recap=False,
        prefers_examples_first=True,
        overload_risk="low",
    )


def _ctx_with_signals():
    return LearningMemoryContext(
        active_error_patterns=[_note("e1", ["sp-x"])],
        mastery_signals=[_note("m1", ["sp-y"])],
    )


def test_format_memory_for_prompt_labels_each_bucket():
    from app.langgraph.planner.graphs.generate_roadmap.nodes import (
        _format_memory_for_prompt,
    )

    text = _format_memory_for_prompt(_ctx_with_signals())
    low = text.lower()
    assert "error pattern" in low
    assert "mastery signal" in low


def test_format_memory_for_prompt_handles_empty_context():
    from app.langgraph.planner.graphs.generate_roadmap.nodes import (
        _format_memory_for_prompt,
    )

    text = _format_memory_for_prompt(LearningMemoryContext())
    assert isinstance(text, str)
    assert text.strip() != ""  # should render a "no memory" placeholder


def test_retrieve_goal_memory_populates_state(monkeypatch):
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    sentinel = LearningMemoryContext(relevant_notes=[_note("n1", ["sp-z"])])

    def _fake_retrieve(user_id, query_text):
        assert user_id == "u-1"
        return sentinel

    monkeypatch.setattr(nodes, "_retrieve_memory_context", _fake_retrieve)

    out = nodes.retrieve_goal_memory(
        {"goal_spec": _goal(), "user_id": "u-1", "roadmap_uuid": "r-1"}
    )
    assert out["goal_memory_context"] is sentinel


def test_retrieve_goal_memory_no_user_id_is_noop(monkeypatch):
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    def _boom(*a, **k):
        raise AssertionError("should not retrieve without user_id")

    monkeypatch.setattr(nodes, "_retrieve_memory_context", _boom)
    out = nodes.retrieve_goal_memory({"goal_spec": _goal(), "roadmap_uuid": "r-1"})
    # No user_id -> no retrieval, empty/no context, no crash
    assert out.get("goal_memory_context") is None


def test_generate_milestone_injects_goal_memory_into_prompt(monkeypatch):
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    captured = {}

    class _FakeStructured:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return nodes.MilestoneResponse(milestones=[])

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _FakeStructured()

    monkeypatch.setattr(nodes, "get_gemini", lambda: _FakeLLM())

    nodes.generate_milestone(
        {
            "roadmap_uuid": "r-1",
            "goal_spec": _goal(),
            "learning_profile": _profile(),
            "goal_memory_context": _ctx_with_signals(),
        }
    )
    assert "mastery signal" in captured["prompt"].lower()


def _no_retrieve(*_a, **_k):
    raise AssertionError("review/revise nodes must not re-retrieve memory")


def test_quick_review_injects_memory_without_reretrieval(monkeypatch):
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    captured = {}

    class _FakeStructured:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return nodes.QuickReviewResponse(proceed=True, summary="ok", findings=[])

    monkeypatch.setattr(
        nodes,
        "get_gemini",
        lambda: type(
            "L", (), {"with_structured_output": lambda self, s: _FakeStructured()}
        )(),
    )
    monkeypatch.setattr(nodes, "_retrieve_memory_context", _no_retrieve)

    milestone = MilestoneItem(
        roadmap_uuid="r-1",
        milestone_id="m-1",
        title="Async",
        description="d",
        objective="o",
        estimated_hours=2.0,
        order_index=1,
    )
    nodes.milestone_quick_review(
        {
            "goal_spec": _goal(),
            "learning_profile": _profile(),
            "milestones": [milestone],
            "goal_memory_context": _ctx_with_signals(),
        }
    )
    assert "mastery signal" in captured["prompt"].lower()


def test_revise_milestones_injects_memory_without_reretrieval(monkeypatch):
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    captured = {}

    class _FakeStructured:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return nodes.MilestoneResponse(milestones=[])

    monkeypatch.setattr(
        nodes,
        "get_gemini",
        lambda: type(
            "L", (), {"with_structured_output": lambda self, s: _FakeStructured()}
        )(),
    )
    monkeypatch.setattr(nodes, "_retrieve_memory_context", _no_retrieve)

    from app.langgraph.planner.schema.review import QuickReviewResponse, ReviewFinding

    milestone = MilestoneItem(
        roadmap_uuid="r-1",
        milestone_id="m-1",
        title="Async",
        description="d",
        objective="o",
        estimated_hours=2.0,
        order_index=1,
    )
    review = QuickReviewResponse(
        proceed=False,
        summary="needs revision",
        findings=[
            ReviewFinding(
                level="major",
                target_type="milestone",
                target_id="m-1",
                issue_type="scope",
                reason="too broad",
                suggested_action="split",
            )
        ],
    )

    nodes.revise_milestones(
        {
            "roadmap_uuid": "r-1",
            "goal_spec": _goal(),
            "learning_profile": _profile(),
            "milestones": [milestone],
            "milestone_quick_review": review,
            "milestone_revision_count": 0,
            "goal_memory_context": _ctx_with_signals(),
        }
    )
    assert "mastery signal" in captured["prompt"].lower()


def test_skillpath_worker_injects_milestone_prompt_context(monkeypatch):
    """Worker is pure-sync: it injects the milestone_prompt_context delivered in its
    Send payload (retrieval + rerank happen in the pre-fan-out node, not here)."""
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    captured = {}

    class _FakeStructured:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return nodes.SkillPathResponse(skillpaths=[])

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _FakeStructured()

    monkeypatch.setattr(nodes, "get_gemini", lambda: _FakeLLM())

    milestone_ctx = LearningMemoryContext(mastery_signals=[_note("m1", ["sp-y"])])
    milestone = MilestoneItem(
        roadmap_uuid="r-1",
        milestone_id="m-1",
        title="Async",
        description="d",
        objective="o",
        estimated_hours=2.0,
        order_index=1,
    )
    out = nodes.skillpath_worker(
        {
            "roadmap_uuid": "r-1",
            "goal_spec": _goal(),
            "learning_profile": _profile(),
            "milestone": milestone,
            "milestone_prompt_context": milestone_ctx,
        }
    )
    assert "skillpath_drafts" in out
    assert "mastery signal" in captured["prompt"].lower()
