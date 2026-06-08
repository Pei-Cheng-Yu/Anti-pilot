from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.adk_agents.content_generator.prompts import build_content_generation_prompt
from app.adk_agents.content_generator.schemas import (
    AdkContentGenerationOutput,
    AdkContentGenerationRequest,
)
from app.langgraph.content_generation.graphs.generate_learning_content.graph import (
    build_learning_content_graph,
)
from app.schema.entities import (
    ContentGenerationPlan,
    GoalSpec,
    LearnerMemoryNote,
    LearningMemoryContext,
    LearningProfile,
    MemoryRerankResult,
    MilestoneItem,
    SelectedMemoryMetadata,
    SkillPathItem,
)
from app.schema.enums import (
    ExampleStyle,
    LearningContentType,
    MemoryRerankPurpose,
    MemoryType,
    PracticeMode,
    TeachingAction,
)
from app.services import memory_service
from dotenv import load_dotenv

# Keep test environment behavior aligned with the other graph-level tests.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _fake_generate_skillpath_content(request) -> AdkContentGenerationOutput:
    # Deterministic marker output for non-live graph tests. If this text appears
    # in LangSmith, the trace is from a fake/unit path, not real ADK generation.
    article = {
        "title": "Read the concept",
        "description": "Short article for the skill path.",
        "skill_intro": "This skill matters because it unlocks later work.",
        "reading_content": "Core explanation with a small worked example.",
        "references": [
            {
                "title": "Python Docs",
                "url": "https://docs.python.org/3/",
            }
        ],
        "source_notes": [
            {
                "source": {
                    "title": "Python Docs",
                    "url": "https://docs.python.org/3/",
                },
                "note": "Used for core terminology.",
            }
        ],
    }

    if request.skillpath.practice_mode == PracticeMode.CODING_PROBLEM:
        return AdkContentGenerationOutput(
            article=article,
            coding_problem={
                "title": "Practice implementation",
                "description": "Hands-on coding practice.",
                "prompt": "Implement the required behavior.",
                "difficulty": "easy",
                "starter_code": "def solve():\n    pass",
                "expected_output": "Expected behavior",
                "hints": ["Start small"],
            },
        )

    return AdkContentGenerationOutput(
        article=article,
        multiple_choice={
            "title": "Quick concept check",
            "description": "Short multiple-choice validation.",
            "question": "Which statement is correct?",
            "options": [
                {"option_id": "A", "text": "Option A"},
                {"option_id": "B", "text": "Option B"},
                {"option_id": "C", "text": "Option C"},
            ],
            "correct_option_id": "B",
            "explanation": "B is the best answer for this scenario.",
        },
    )


def _make_goal() -> GoalSpec:
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
        constraints=["6 hours per week", "Prefer hands-on learning"],
    )


def _make_profile() -> LearningProfile:
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


def _make_state() -> dict:
    roadmap_id = "roadmap-test"
    milestone_id = str(uuid4())
    return {
        "goal_spec": _make_goal(),
        "learning_profile": _make_profile(),
        "milestones": [
            MilestoneItem(
                roadmap_uuid=roadmap_id,
                milestone_id=milestone_id,
                title="Build APIs",
                description="Core API implementation work.",
                objective="Understand and build backend endpoints.",
                estimated_hours=12.0,
                order_index=1,
                status="generated",
                need_modification=False,
                revision_reason=None,
            )
        ],
        "skillpaths": [
            SkillPathItem(
                skillpath_id="sp-1",
                milestone_id=milestone_id,
                title="HTTP Basics",
                description="Learn request and response fundamentals.",
                estimated_hours=3.0,
                prerequisite_skillpath_ids=[],
                learning_objectives=["Understand HTTP methods"],
                status="ready",
                need_generation=True,
                need_modification=False,
                practice_mode=PracticeMode.MULTIPLE_CHOICE,
            ),
            SkillPathItem(
                skillpath_id="sp-2",
                milestone_id=milestone_id,
                title="FastAPI Route Handlers",
                description="Implement API route handlers.",
                estimated_hours=4.0,
                prerequisite_skillpath_ids=["sp-1"],
                learning_objectives=["Write route handlers"],
                status="ready",
                need_generation=True,
                need_modification=False,
            ),
        ],
        "content_drafts": [],
        "content_plan": ContentGenerationPlan(
            article_depth=None,
            example_style=ExampleStyle.EXAMPLE_FIRST,
            include_recap=False,
        ),
    }


def test_learning_content_graph_generates_article_and_practice(monkeypatch):
    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes.generate_skillpath_content",
        _fake_generate_skillpath_content,
    )

    graph = build_learning_content_graph()
    result = graph.invoke(_make_state())
    generated_skillpaths = result["generated_skillpaths"]

    assert len(generated_skillpaths) == 2

    first = next(sp for sp in generated_skillpaths if sp.skillpath_id == "sp-1")
    second = next(sp for sp in generated_skillpaths if sp.skillpath_id == "sp-2")

    assert first.need_generation is False
    assert second.need_generation is False
    assert len(first.learning_contents) == 2
    assert len(second.learning_contents) == 2
    assert first.learning_contents[0].content_type == LearningContentType.ARTICLE
    assert second.learning_contents[0].content_type == LearningContentType.ARTICLE
    assert (
        first.learning_contents[1].content_type == LearningContentType.MULTIPLE_CHOICE
    )
    assert (
        second.learning_contents[1].content_type == LearningContentType.CODING_PROBLEM
    )


def test_learning_content_graph_passes_memory_context_to_generator(monkeypatch):
    captured_contexts = []

    def fake_generate_with_memory(request):
        captured_contexts.append(request.learning_memory_context)
        return _fake_generate_skillpath_content(request)

    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes.generate_skillpath_content",
        fake_generate_with_memory,
    )
    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes._retrieve_learning_memory_context",
        lambda *_args, **_kwargs: LearningMemoryContext(),
        raising=False,
    )

    state = _make_state()
    state["user_id"] = "user-1"

    graph = build_learning_content_graph()
    graph.invoke(state)

    assert captured_contexts
    assert all(context is not None for context in captured_contexts)


def _make_memory_context() -> LearningMemoryContext:
    return LearningMemoryContext(
        active_error_patterns=[
            LearnerMemoryNote(
                memory_id="mem-fastapi-await",
                user_id="user-1",
                memory_type=MemoryType.ERROR_PATTERN,
                title="FastAPI missing await pattern",
                summary=(
                    "Learner repeatedly forgets to await async database calls inside "
                    "FastAPI route handlers."
                ),
                tags=["fastapi", "async", "await"],
                linked_concepts=["fastapi.async", "missing await"],
                linked_skillpath_ids=["sp-2"],
                linked_content_ids=["cp-fastapi-await"],
                evidence_attempt_ids=["attempt-1", "attempt-2"],
                salience_score=0.9,
                created_at=datetime.now(timezone.utc),
            )
        ],
        teaching_heuristics=[
            LearnerMemoryNote(
                memory_id="mem-fastapi-await-heuristic",
                user_id="user-1",
                memory_type=MemoryType.HEURISTIC,
                title="Pause on coroutine boundaries",
                summary=(
                    "When teaching FastAPI routes, ask the learner to identify every "
                    "async call site before writing the return statement."
                ),
                tags=["fastapi", "async", "heuristic"],
                linked_concepts=["fastapi.async"],
                linked_skillpath_ids=["sp-2"],
                evidence_attempt_ids=["attempt-1", "attempt-2"],
                salience_score=0.8,
                created_at=datetime.now(timezone.utc),
            )
        ],
        relevant_notes=[],
    )


def test_learning_content_prompt_includes_seeded_memory_context(monkeypatch):
    captured_requests: list[AdkContentGenerationRequest] = []
    seeded_context = _make_memory_context()

    def fake_generate_with_memory(request):
        captured_requests.append(request)
        return _fake_generate_skillpath_content(request)

    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes.generate_skillpath_content",
        fake_generate_with_memory,
    )
    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes._retrieve_learning_memory_context",
        lambda *_args, **_kwargs: seeded_context,
        raising=False,
    )

    state = _make_state()
    state["user_id"] = "user-1"

    graph = build_learning_content_graph()
    result = graph.invoke(state)

    request = next(
        item for item in captured_requests if item.skillpath.skillpath_id == "sp-2"
    )
    contexts_by_skillpath = result["learning_memory_contexts_by_skillpath"]
    state_context = contexts_by_skillpath["sp-2"]
    diagnostics = result["learning_memory_retrieval_diagnostics_by_skillpath"]
    diagnostic = diagnostics["sp-2"]
    prompt = build_content_generation_prompt(request)

    assert request.learning_memory_context is not None
    assert request.learning_memory_context.active_error_patterns[0].memory_id == (
        "mem-fastapi-await"
    )
    assert state_context.model_dump() == request.learning_memory_context.model_dump()
    assert state_context.active_error_patterns[0].memory_id == "mem-fastapi-await"
    assert diagnostic.status == "retrieved"
    assert diagnostic.user_id_present is True
    assert diagnostic.active_error_pattern_count == 1
    assert diagnostic.teaching_heuristic_count == 1
    assert "Learner memory context" in prompt
    assert "FastAPI missing await pattern" in prompt
    assert "await async database calls" in prompt


def test_learning_content_graph_reranks_memory_context_for_generation(monkeypatch):
    captured_requests: list[AdkContentGenerationRequest] = []
    captured_rerank_requests = []
    seeded_context = _make_memory_context()

    def fake_generate_with_memory(request):
        captured_requests.append(request)
        return _fake_generate_skillpath_content(request)

    async def fake_rerank_memories(request, *, advisor=None):
        captured_rerank_requests.append(request)
        selected_note = seeded_context.active_error_patterns[0]
        return MemoryRerankResult(
            purpose=MemoryRerankPurpose.CONTENT_GENERATION,
            selected_memories=[
                SelectedMemoryMetadata(
                    memory_id=selected_note.memory_id,
                    memory_type=selected_note.memory_type,
                    title=selected_note.title,
                    reason="Use this error pattern to shape the new lesson.",
                )
            ],
            teaching_action=TeachingAction.QUICK_RECAP_THEN_HINT,
            focused_concepts=["fastapi.async", "missing await"],
            guidance="Start with a short recap about awaiting async DB calls.",
        )

    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes.generate_skillpath_content",
        fake_generate_with_memory,
    )
    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes._retrieve_learning_memory_context",
        lambda *_args, **_kwargs: seeded_context,
        raising=False,
    )
    monkeypatch.setattr(memory_service, "rerank_memories", fake_rerank_memories)

    state = _make_state()
    state["user_id"] = "user-1"

    graph = build_learning_content_graph()
    result = graph.invoke(state)

    assert captured_rerank_requests
    assert all(
        request.purpose == MemoryRerankPurpose.CONTENT_GENERATION
        for request in captured_rerank_requests
    )
    sp2_request = next(
        item for item in captured_requests if item.skillpath.skillpath_id == "sp-2"
    )
    assert sp2_request.memory_rerank_result is not None
    assert sp2_request.memory_rerank_result.selected_memory_ids == ["mem-fastapi-await"]
    diagnostics = result["learning_memory_rerank_diagnostics_by_skillpath"]
    assert diagnostics["sp-2"].status == "reranked"
    assert diagnostics["sp-2"].selected_memory_ids == ["mem-fastapi-await"]


def test_learning_content_graph_reports_skipped_memory_without_user(monkeypatch):
    captured_requests: list[AdkContentGenerationRequest] = []

    def fake_generate_with_memory(request):
        captured_requests.append(request)
        return _fake_generate_skillpath_content(request)

    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes.generate_skillpath_content",
        fake_generate_with_memory,
    )

    graph = build_learning_content_graph()
    result = graph.invoke(_make_state())

    assert captured_requests
    assert all(request.learning_memory_context is None for request in captured_requests)
    assert result.get("learning_memory_contexts_by_skillpath", {}) == {}
    diagnostics = result["learning_memory_retrieval_diagnostics_by_skillpath"]
    assert set(diagnostics) == {"sp-1", "sp-2"}
    assert all(item.status == "skipped_no_user_id" for item in diagnostics.values())
    assert all(item.user_id_present is False for item in diagnostics.values())


def test_learning_content_graph_reports_empty_memory_context(monkeypatch):
    captured_requests: list[AdkContentGenerationRequest] = []

    def fake_generate_with_memory(request):
        captured_requests.append(request)
        return _fake_generate_skillpath_content(request)

    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes.generate_skillpath_content",
        fake_generate_with_memory,
    )
    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes._retrieve_learning_memory_context",
        lambda *_args, **_kwargs: LearningMemoryContext(),
        raising=False,
    )

    state = _make_state()
    state["user_id"] = "user-1"

    graph = build_learning_content_graph()
    result = graph.invoke(state)

    assert captured_requests
    diagnostics = result["learning_memory_retrieval_diagnostics_by_skillpath"]
    assert set(diagnostics) == {"sp-1", "sp-2"}
    assert all(item.status == "retrieved_empty" for item in diagnostics.values())
    assert all(item.user_id_present is True for item in diagnostics.values())
    assert all(item.relevant_note_count == 0 for item in diagnostics.values())
    rerank_diagnostics = result["learning_memory_rerank_diagnostics_by_skillpath"]
    assert set(rerank_diagnostics) == {"sp-1", "sp-2"}
    assert all(
        item.status == "skipped_no_memory" for item in rerank_diagnostics.values()
    )
    assert all(item.candidate_memory_count == 0 for item in rerank_diagnostics.values())


def test_learning_content_graph_reports_failed_memory_retrieval(monkeypatch):
    captured_requests: list[AdkContentGenerationRequest] = []

    def fake_generate_with_memory(request):
        captured_requests.append(request)
        return _fake_generate_skillpath_content(request)

    def fail_retrieval(*_args, **_kwargs):
        raise RuntimeError("memory database unavailable")

    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes.generate_skillpath_content",
        fake_generate_with_memory,
    )
    monkeypatch.setattr(
        "app.langgraph.content_generation.graphs.generate_learning_content.nodes._retrieve_learning_memory_context",
        fail_retrieval,
        raising=False,
    )

    state = _make_state()
    state["user_id"] = "user-1"

    graph = build_learning_content_graph()
    result = graph.invoke(state)

    assert captured_requests
    assert all(request.learning_memory_context is None for request in captured_requests)
    diagnostics = result["learning_memory_retrieval_diagnostics_by_skillpath"]
    assert set(diagnostics) == {"sp-1", "sp-2"}
    assert all(item.status == "failed" for item in diagnostics.values())
    assert all(item.user_id_present is True for item in diagnostics.values())
    assert all(
        "memory database unavailable" in (item.error_summary or "")
        for item in diagnostics.values()
    )


def _print_skillpath_contents(result: dict) -> None:
    generated_skillpaths = result.get("generated_skillpaths", [])
    print("\n=== GENERATED LEARNING CONTENT ===")
    print(f"skillpaths: {len(generated_skillpaths)}")
    for skillpath in generated_skillpaths:
        print(f"\n--- {skillpath.title} ({skillpath.skillpath_id}) ---")
        for content in skillpath.learning_contents:
            print(f"{content.content_type.value}: {content.title}")
            if content.content_type == LearningContentType.ARTICLE:
                print(content.skill_intro)
                print(content.reading_content)
                if content.references:
                    print("references:")
                    for ref in content.references:
                        print(f"- {ref.title}: {ref.url}")
            elif content.content_type == LearningContentType.CODING_PROBLEM:
                print(content.prompt)
            elif content.content_type == LearningContentType.MULTIPLE_CHOICE:
                print(content.question)


def main() -> None:
    print("Starting learning content smoke test")
    print("This run uses the real content-generation graph and ADK agent.")
    graph = build_learning_content_graph()
    result = graph.invoke(deepcopy(_make_state()))
    _print_skillpath_contents(result)


if __name__ == "__main__":
    main()
