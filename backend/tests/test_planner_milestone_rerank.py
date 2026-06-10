"""Tests for milestone-level memory rerank in the planner.

Pure/isolated: no DB, no live LLM. The rerank advisor and get_gemini are faked.
"""

from datetime import UTC, datetime

from app.schema.entities import (
    LearnerMemoryNote,
    LearningMemoryContext,
    MemoryRerankRequest,
    MemoryRerankResult,
    SelectedMemoryMetadata,
)
from app.schema.enums import MemoryRerankPurpose, MemoryStatus, MemoryType


def _note(memory_id, title="t"):
    return LearnerMemoryNote(
        memory_id=memory_id,
        user_id="u-1",
        memory_type=MemoryType.ERROR_PATTERN,
        title=title,
        summary="s",
        linked_skillpath_ids=[],
        status=MemoryStatus.ACTIVE,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


def test_roadmap_planning_purpose_exists_and_validates():
    req = MemoryRerankRequest(
        purpose=MemoryRerankPurpose.ROADMAP_PLANNING,
        task_context="Async milestone",
        candidate_memories=[_note("n1")],
        max_selected=5,
    )
    assert req.purpose is MemoryRerankPurpose.ROADMAP_PLANNING
    assert MemoryRerankPurpose.ROADMAP_PLANNING.value == "roadmap_planning"


def test_rerank_prompt_includes_planning_guidance():
    from app.advisors import memory_advisors

    prompt = memory_advisors.build_rerank_advisor_prompt(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.ROADMAP_PLANNING,
            task_context="Async milestone: use await",
            candidate_memories=[_note("n1")],
        )
    )
    assert "roadmap_planning" in prompt
    # Planning-specific guidance mentions skillpaths / milestone scoping.
    low = prompt.lower()
    assert "skillpath" in low or "milestone" in low


# ----------------------------------------------------------------------------
# Group 2/3: skillpath_worker applies rerank selection to the prompt
# ----------------------------------------------------------------------------

from datetime import date  # noqa: E402

from app.schema.entities import GoalSpec, LearningProfile, MilestoneItem  # noqa: E402


def _goal():
    return GoalSpec(
        title="g",
        description="d",
        target_outcome="o",
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


def _milestone():
    return MilestoneItem(
        roadmap_uuid="r-1",
        milestone_id="m-1",
        title="Async",
        description="d",
        objective="use await",
        estimated_hours=2.0,
        order_index=1,
    )


def _make_llm_capture(captured):
    class _FakeStructured:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            from app.langgraph.planner.graphs.generate_roadmap import nodes

            return nodes.SkillPathResponse(skillpaths=[])

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _FakeStructured()

    return _FakeLLM()


def test_worker_is_pure_sync_and_injects_payload_context(monkeypatch):
    """skillpath_worker does NO retrieval/rerank itself — it injects the pre-computed
    milestone_prompt_context from its Send payload. It must not touch the async
    helpers (which would re-introduce the loop-bound-client deadlock)."""
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    keep = _note("keep-1", title="KEEP ASYNC NOTE")
    prompt_ctx = LearningMemoryContext(active_error_patterns=[keep])

    captured = {}
    monkeypatch.setattr(nodes, "get_gemini", lambda: _make_llm_capture(captured))

    def _boom(*a, **k):
        raise AssertionError("worker must not retrieve/rerank — done pre-fan-out")

    monkeypatch.setattr(nodes, "_retrieve_memory_context", _boom)
    monkeypatch.setattr(nodes, "arerank_memories", _boom, raising=False)

    out = nodes.skillpath_worker(
        {
            "roadmap_uuid": "r-1",
            "goal_spec": _goal(),
            "learning_profile": _profile(),
            "milestone": _milestone(),
            "milestone_prompt_context": prompt_ctx,
        }
    )
    assert "KEEP ASYNC NOTE" in captured["prompt"]
    assert "skillpath_drafts" in out


def test_worker_no_prompt_context_does_not_crash(monkeypatch):
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    captured = {}
    monkeypatch.setattr(nodes, "get_gemini", lambda: _make_llm_capture(captured))

    out = nodes.skillpath_worker(
        {
            "roadmap_uuid": "r-1",
            "goal_spec": _goal(),
            "learning_profile": _profile(),
            "milestone": _milestone(),
            # no milestone_prompt_context
        }
    )
    assert "skillpath_drafts" in out
    # Renders the "no memory" placeholder, not a crash.
    assert captured["prompt"]


def test_retrieve_and_rerank_populates_state(monkeypatch):
    """The pre-fan-out node retrieves + reranks all milestones in one event loop and
    stores per-milestone full context + selected ids in state."""
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    keep = _note("keep-1", title="KEEP")
    drop = _note("drop-1", title="DROP")
    ctx = LearningMemoryContext(
        relevant_notes=[keep, drop], active_error_patterns=[keep, drop]
    )

    async def _fake_retrieve(payload, session):
        return ctx

    async def _fake_rerank(request, *, advisor=None):
        return MemoryRerankResult(
            purpose=MemoryRerankPurpose.ROADMAP_PLANNING,
            selected_memories=[
                SelectedMemoryMetadata(
                    memory_id="keep-1",
                    memory_type=MemoryType.ERROR_PATTERN,
                    title="KEEP",
                )
            ],
        )

    monkeypatch.setattr(
        nodes.memory_service, "retrieve_learning_memory", _fake_retrieve
    )
    monkeypatch.setattr(nodes, "arerank_memories", _fake_rerank)

    m1 = _milestone()
    m2 = MilestoneItem(
        roadmap_uuid="r-1",
        milestone_id="m-2",
        title="SQL",
        description="d",
        objective="joins",
        estimated_hours=2.0,
        order_index=2,
    )
    out = nodes.retrieve_and_rerank_milestones(
        {"user_id": "u-1", "milestones": [m1, m2], "roadmap_uuid": "r-1"}
    )
    assert set(out["milestone_memory_contexts"]) == {"m-1", "m-2"}
    assert out["milestone_selected_ids"]["m-1"] == ["keep-1"]
    assert out["milestone_selected_ids"]["m-2"] == ["keep-1"]


def test_retrieve_and_rerank_degrades_per_milestone(monkeypatch):
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    ctx = LearningMemoryContext(relevant_notes=[_note("n1")])

    async def _retrieve_one_fails(payload, session):
        # Fail for m-2 only (query_text contains the milestone title).
        if "SQL" in payload.query_text:
            raise RuntimeError("retrieval failed for this milestone")
        return ctx

    async def _fake_rerank(request, *, advisor=None):
        return MemoryRerankResult(
            purpose=MemoryRerankPurpose.ROADMAP_PLANNING, selected_memories=[]
        )

    monkeypatch.setattr(
        nodes.memory_service, "retrieve_learning_memory", _retrieve_one_fails
    )
    monkeypatch.setattr(nodes, "arerank_memories", _fake_rerank)

    m1 = _milestone()  # title "Async"
    m2 = MilestoneItem(
        roadmap_uuid="r-1",
        milestone_id="m-2",
        title="SQL",
        description="d",
        objective="joins",
        estimated_hours=2.0,
        order_index=2,
    )
    out = nodes.retrieve_and_rerank_milestones(
        {"user_id": "u-1", "milestones": [m1, m2], "roadmap_uuid": "r-1"}
    )
    # m-1 succeeded, m-2 degraded out (no crash).
    assert "m-1" in out["milestone_memory_contexts"]
    assert "m-2" not in out["milestone_memory_contexts"]


def test_route_to_skillpath_workers_builds_filtered_payloads():
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    keep = _note("keep-1", title="KEEP")
    drop = _note("drop-1", title="DROP")
    ctx = LearningMemoryContext(
        active_error_patterns=[keep, drop], relevant_notes=[keep, drop]
    )

    sends = nodes.route_to_skillpath_workers(
        {
            "roadmap_uuid": "r-1",
            "goal_spec": _goal(),
            "learning_profile": _profile(),
            "milestones": [_milestone()],
            "milestone_memory_contexts": {"m-1": ctx},
            "milestone_selected_ids": {"m-1": ["keep-1"]},
        }
    )
    assert len(sends) == 1
    payload = sends[0].arg
    filtered = payload["milestone_prompt_context"]
    titles = [n.title for n in filtered.active_error_patterns]
    assert titles == ["KEEP"]  # drop-1 filtered out


def test_rerank_helper_deterministic_when_flag_disabled(monkeypatch):
    """With the rerank flag off, _rerank_milestone_memory returns the deterministic
    top-N (first max_selected by order) without invoking any LLM."""
    from app.langgraph.planner.graphs.generate_roadmap import nodes

    monkeypatch.delenv("ENABLE_MEMORY_RERANK_ADVISOR", raising=False)
    notes = [_note(f"n{i}", title=f"NOTE {i}") for i in range(8)]
    result = nodes._rerank_milestone_memory(notes, _milestone())
    # Deterministic fallback selects the first max_selected (5) by order.
    assert [m.memory_id for m in result.selected_memories] == [
        f"n{i}" for i in range(5)
    ]
