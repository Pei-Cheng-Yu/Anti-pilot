from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.db.model import ReviewConceptModel
from app.routers.reviews import (
    ReviewGradeRequest,
    generate_task_for_concept,
    get_all_reviews,
    get_due_reviews,
    grade_review,
)
from app.langgraph.learning_director import agent as learning_director_agent
from app.schema.entities import (
    GoalSpec,
    LearningProfile,
    MilestoneItem,
    MilestoneWithSkillPaths,
    RoadmapFull,
    RoadmapItem,
    SkillPathItem,
)
from app.services.roadmap import _toposort_skillpaths
from fastapi.testclient import TestClient

client = TestClient(app)


@asynccontextmanager
async def fake_session():
    yield MagicMock()


def make_goal() -> GoalSpec:
    return GoalSpec(
        title="Learn Testing",
        description="Learn how to write tests",
        target_outcome="Write good tests",
        deadline=date(2026, 12, 31),
        criteria=["Write 10 tests"],
        constraints=["1 hour/day"],
    )


def make_profile() -> LearningProfile:
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


def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "status": "online",
        "message": "AntiCopilot API is running",
    }


def test_roadmap_title_and_id_aliases_are_preserved():
    roadmap = RoadmapItem(
        roadmap_id="r1",
        title="Readable Roadmap",
        version=1,
        summary="Summary",
        target_outcome="Outcome",
    )
    assert roadmap.title == "Readable Roadmap"
    assert roadmap.model_dump()["title"] == "Readable Roadmap"

    milestone = MilestoneItem(
        roadmap_uuid="r1",
        milestone_id="m1",
        title="Milestone",
        description="Desc",
        objective="Obj",
        estimated_hours=1,
        order_index=1,
    )
    assert milestone.roadmap_id == "r1"
    assert milestone.roadmap_uuid == "r1"
    assert milestone.model_dump()["roadmap_id"] == "r1"


def test_get_roadmap(monkeypatch):
    async def fake_get_roadmap_full(user_id, roadmap_id, session):
        return RoadmapFull(
            roadmap_id=roadmap_id,
            title="Test Roadmap",
            version=1,
            summary="Test roadmap",
            target_outcome="Ship tests",
            assumptions=[],
            milestones=[
                MilestoneWithSkillPaths(
                    roadmap_id=roadmap_id,
                    milestone_id="m1",
                    title="Milestone 1",
                    description="Desc",
                    objective="Obj",
                    estimated_hours=1,
                    order_index=1,
                    skillpaths=[],
                )
            ],
        )

    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr(
        "app.main.roadmap_service.get_roadmap_full", fake_get_roadmap_full
    )

    response = client.get("/v1/roadmaps/test-roadmap")
    assert response.status_code == 200
    data = response.json()
    assert data["roadmap_id"] == "test-roadmap"
    assert data["title"] == "Test Roadmap"
    assert len(data["milestones"]) == 1


def test_get_roadmap_not_found(monkeypatch):
    async def fake_get_roadmap_full(user_id, roadmap_id, session):
        raise ValueError("not found")

    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr(
        "app.main.roadmap_service.get_roadmap_full", fake_get_roadmap_full
    )

    response = client.get("/v1/roadmaps/non-existent-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Roadmap not found"


@patch("app.main.build_planner_graph")
def test_create_goal(mock_build_planner, monkeypatch):
    mock_planner = MagicMock()
    mock_build_planner.return_value = mock_planner

    roadmap = RoadmapItem(
        roadmap_id="roadmap-1",
        title="Test Roadmap",
        version=1,
        summary="A test roadmap",
        target_outcome="Write good tests",
        assumptions=[],
    )
    milestone = MilestoneItem(
        roadmap_id="roadmap-1",
        milestone_id="m1",
        title="Milestone 1",
        description="Desc",
        objective="Obj",
        estimated_hours=1,
        order_index=1,
        status="generated",
    )
    skillpath = SkillPathItem(
        roadmap_id="roadmap-1",
        skillpath_id="s1",
        milestone_id="m1",
        title="Skillpath 1",
        description="Desc",
        estimated_hours=1,
        status="ready",
    )
    mock_planner.invoke.return_value = {
        "roadmap": roadmap,
        "milestones": [milestone],
        "skillpaths": [skillpath],
    }

    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr("app.main.goal_service.save_goal", AsyncMock())
    monkeypatch.setattr(
        "app.main.learning_profile_service.save_learning_profile", AsyncMock()
    )
    monkeypatch.setattr("app.main.roadmap_service.save_roadmap", AsyncMock())

    response = client.post(
        "/v1/goals",
        json={
            "goal_spec": make_goal().model_dump(mode="json"),
            "learning_profile": make_profile().model_dump(mode="json"),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "roadmap_id" in data
    assert data["roadmap"]["title"] == "Test Roadmap"
    assert data["roadmap"]["summary"] == "A test roadmap"
    assert len(data["milestones"]) == 1


def test_report_struggle(monkeypatch):
    signal_session = None

    class FakeSession:
        def add(self, row):
            self.row = row

        async def commit(self):
            return None

    @asynccontextmanager
    async def fake_signal_session():
        nonlocal signal_session
        signal_session = FakeSession()
        yield signal_session

    monkeypatch.setattr("app.routers.signals.get_session", fake_signal_session)
    monkeypatch.setattr(
        "app.routers.signals.get_gemini",
        lambda: SimpleNamespace(
            invoke=lambda messages: SimpleNamespace(
                content='{"hint":"Check the branch condition.","concept_name":"Conditionals","misconception":"The false path was ignored."}'
            )
        ),
    )

    response = client.post(
        "/v1/signals/struggle",
        json={
            "roadmap_id": "test-roadmap",
            "user_id": "user-123",
            "milestone_id": "m1",
            "skillpath_id": "s1",
            "code_context": "def foo(): pass",
            "diagnostic_message": "Error at line 1",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["hint"] == "Check the branch condition."
    assert data["concept_name"] == "Conditionals"
    assert data["action_required"] is True
    assert signal_session.row.user_id == "user-123"


class FakeReviewResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return iter(self.rows)

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None


class FakeReviewSession:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []
        self.committed = False

    async def execute(self, query):
        self.queries.append(str(query))
        return FakeReviewResult(self.rows)

    async def commit(self):
        self.committed = True


def make_review_row(user_id: str = "user-123") -> ReviewConceptModel:
    now = datetime.now(timezone.utc)
    return ReviewConceptModel(
        concept_id="concept-1",
        user_id=user_id,
        source_type="skill_path",
        source_ref_id="content-1",
        concept_metadata={"concept_name": "HTTP Methods"},
        state=1,
        due=now,
        stability=4.0,
        difficulty=5.0,
        updated_at=now,
        elapsed_days=0,
        scheduled_days=0,
        reps=1,
        lapses=0,
    )


def scoped_review_session(monkeypatch, rows):
    session = FakeReviewSession(rows)

    @asynccontextmanager
    async def fake_review_session():
        yield session

    monkeypatch.setattr("app.routers.reviews.get_session", fake_review_session)
    return session


async def test_review_list_endpoints_are_user_scoped(monkeypatch):
    row = make_review_row()
    session = scoped_review_session(monkeypatch, [row])

    all_reviews = await get_all_reviews(user_id="user-123")
    due_reviews = await get_due_reviews(user_id="user-123")

    assert all_reviews[0]["user_id"] == "user-123"
    assert due_reviews[0]["user_id"] == "user-123"
    assert all("review_concepts.user_id" in query for query in session.queries)


async def test_review_grade_is_user_scoped(monkeypatch):
    row = make_review_row()
    session = scoped_review_session(monkeypatch, [row])

    result = await grade_review(
        "concept-1", ReviewGradeRequest(grade=3), user_id="user-123"
    )

    assert result["user_id"] == "user-123"
    assert row.reps == 2
    assert session.committed is True
    assert "review_concepts.user_id" in session.queries[0]


async def test_review_task_generation_is_user_scoped(monkeypatch):
    row = make_review_row()
    session = scoped_review_session(monkeypatch, [row])
    monkeypatch.setattr(
        "app.routers.reviews.get_gemini",
        lambda: SimpleNamespace(
            invoke=lambda messages: SimpleNamespace(
                content="### Task\nExplain GET vs POST.\n### Solution\nGET reads; POST submits."
            )
        ),
    )

    result = await generate_task_for_concept("concept-1", user_id="user-123")

    assert result.task_type == "coding_snippet"
    assert "GET vs POST" in result.content
    assert "review_concepts.user_id" in session.queries[0]


def test_learning_director_planner_accepts_roadmap_uuid():
    assert (
        learning_director_agent.planner_roadmap_id({"roadmap_uuid": "roadmap-uuid-1"})
        == "roadmap-uuid-1"
    )


def test_generate_roadmap_content(monkeypatch):
    roadmap_id = "roadmap-1"
    skillpath = SkillPathItem(
        roadmap_id=roadmap_id,
        skillpath_id="s1",
        milestone_id="m1",
        title="Skillpath 1",
        description="Desc",
        estimated_hours=1,
        status="ready",
        need_generation=True,
    )
    generated_skillpath = skillpath.model_copy(
        update={"status": "generated", "need_generation": False}
    )
    roadmap = RoadmapFull(
        roadmap_id=roadmap_id,
        title="Test Roadmap",
        version=1,
        summary="Test roadmap",
        target_outcome="Ship tests",
        assumptions=[],
        milestones=[
            MilestoneWithSkillPaths(
                roadmap_id=roadmap_id,
                milestone_id="m1",
                title="Milestone 1",
                description="Desc",
                objective="Obj",
                estimated_hours=1,
                order_index=1,
                skillpaths=[skillpath],
            )
        ],
    )
    refreshed = RoadmapFull(
        roadmap_id=roadmap_id,
        title="Test Roadmap",
        version=1,
        summary="Test roadmap",
        target_outcome="Ship tests",
        assumptions=[],
        milestones=[
            MilestoneWithSkillPaths(
                roadmap_id=roadmap_id,
                milestone_id="m1",
                title="Milestone 1",
                description="Desc",
                objective="Obj",
                estimated_hours=1,
                order_index=1,
                skillpaths=[generated_skillpath],
            )
        ],
    )

    class FakeContentGraph:
        def invoke(self, state):
            assert state["goal_spec"].title == "Learn Testing"
            assert len(state["skillpaths"]) == 1
            return {"generated_skillpaths": [generated_skillpath]}

    get_roadmap_full = AsyncMock(side_effect=[roadmap, refreshed])
    save_generated_skillpaths = AsyncMock()

    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr("app.main.goal_service.get_goal", AsyncMock(return_value=make_goal()))
    monkeypatch.setattr(
        "app.main.learning_profile_service.get_learning_profile",
        AsyncMock(return_value=make_profile()),
    )
    monkeypatch.setattr("app.main.roadmap_service.get_roadmap_full", get_roadmap_full)
    monkeypatch.setattr(
        "app.main.roadmap_service.save_generated_skillpaths",
        save_generated_skillpaths,
    )
    monkeypatch.setattr("app.main._content_generator", FakeContentGraph())

    response = client.post(f"/v1/roadmaps/{roadmap_id}/generate-content")
    assert response.status_code == 200
    data = response.json()
    assert data["roadmap_id"] == roadmap_id
    assert data["generated_skillpath_count"] == 1
    assert data["roadmap"]["milestones"][0]["skillpaths"][0]["status"] == "generated"
    save_generated_skillpaths.assert_awaited_once()


def test_generate_roadmap_content_rejects_multi_skillpath_batch(monkeypatch):
    roadmap_id = "roadmap-1"
    skillpaths = [
        SkillPathItem(
            roadmap_id=roadmap_id,
            skillpath_id=f"s{i}",
            milestone_id="m1",
            title=f"Skillpath {i}",
            description="Desc",
            estimated_hours=1,
            status="ready",
            need_generation=True,
        )
        for i in range(2)
    ]
    roadmap = RoadmapFull(
        roadmap_id=roadmap_id,
        title="Test Roadmap",
        version=1,
        summary="Test roadmap",
        target_outcome="Ship tests",
        assumptions=[],
        milestones=[
            MilestoneWithSkillPaths(
                roadmap_id=roadmap_id,
                milestone_id="m1",
                title="Milestone 1",
                description="Desc",
                objective="Obj",
                estimated_hours=1,
                order_index=1,
                skillpaths=skillpaths,
            )
        ],
    )

    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr("app.main.goal_service.get_goal", AsyncMock(return_value=make_goal()))
    monkeypatch.setattr(
        "app.main.learning_profile_service.get_learning_profile",
        AsyncMock(return_value=make_profile()),
    )
    monkeypatch.setattr(
        "app.main.roadmap_service.get_roadmap_full", AsyncMock(return_value=roadmap)
    )

    response = client.post(f"/v1/roadmaps/{roadmap_id}/generate-content")
    assert response.status_code == 409
    assert response.json()["detail"]["pending_skillpath_ids"] == ["s0", "s1"]


def test_generate_skillpath_content(monkeypatch):
    roadmap_id = "roadmap-1"
    skillpath = SkillPathItem(
        roadmap_id=roadmap_id,
        skillpath_id="s1",
        milestone_id="m1",
        title="Skillpath 1",
        description="Desc",
        estimated_hours=1,
        status="ready",
        need_generation=True,
    )
    generated_skillpath = skillpath.model_copy(
        update={"status": "generated", "need_generation": False}
    )
    roadmap = RoadmapFull(
        roadmap_id=roadmap_id,
        title="Test Roadmap",
        version=1,
        summary="Test roadmap",
        target_outcome="Ship tests",
        assumptions=[],
        milestones=[
            MilestoneWithSkillPaths(
                roadmap_id=roadmap_id,
                milestone_id="m1",
                title="Milestone 1",
                description="Desc",
                objective="Obj",
                estimated_hours=1,
                order_index=1,
                skillpaths=[skillpath],
            )
        ],
    )
    refreshed = roadmap.model_copy(
        update={
            "milestones": [
                roadmap.milestones[0].model_copy(
                    update={"skillpaths": [generated_skillpath]}
                )
            ]
        }
    )

    class FakeContentGraph:
        def invoke(self, state):
            assert [item.skillpath_id for item in state["skillpaths"]] == ["s1"]
            return {"generated_skillpaths": [generated_skillpath]}

    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr("app.main.goal_service.get_goal", AsyncMock(return_value=make_goal()))
    monkeypatch.setattr(
        "app.main.learning_profile_service.get_learning_profile",
        AsyncMock(return_value=make_profile()),
    )
    monkeypatch.setattr(
        "app.main.roadmap_service.get_roadmap_full",
        AsyncMock(side_effect=[roadmap, refreshed]),
    )
    monkeypatch.setattr(
        "app.main.roadmap_service.save_generated_skillpaths", AsyncMock()
    )
    monkeypatch.setattr("app.main._content_generator", FakeContentGraph())

    response = client.post(
        f"/v1/roadmaps/{roadmap_id}/skillpaths/s1/generate-content"
    )
    assert response.status_code == 200
    assert response.json()["generated_skillpath_count"] == 1


def _make_skillpath(skillpath_id: str, prereqs: list[str]) -> SkillPathItem:
    return SkillPathItem(
        roadmap_id="roadmap-1",
        skillpath_id=skillpath_id,
        milestone_id="m1",
        title=skillpath_id,
        description="x",
        estimated_hours=1,
        prerequisite_skillpath_ids=prereqs,
        status="ready",
    )


def test_toposort_orders_by_prerequisites():
    skillpaths = [
        _make_skillpath("c", ["b"]),
        _make_skillpath("a", []),
        _make_skillpath("b", ["a"]),
    ]
    ordered = _toposort_skillpaths(skillpaths)
    ids = [sp.skillpath_id for sp in ordered]
    assert ids == ["a", "b", "c"]


def test_toposort_breaks_ties_by_insertion_order():
    skillpaths = [
        _make_skillpath("alpha", []),
        _make_skillpath("beta", []),
        _make_skillpath("gamma", []),
    ]
    ordered = _toposort_skillpaths(skillpaths)
    assert [sp.skillpath_id for sp in ordered] == ["alpha", "beta", "gamma"]


def test_toposort_ignores_cross_milestone_prereqs():
    skillpaths = [
        _make_skillpath("b", ["a"]),
        _make_skillpath("c", ["external-from-other-milestone"]),
    ]
    ordered = _toposort_skillpaths(skillpaths)
    # 'a' isn't in scope so 'b' has no in-scope prereq; same for 'c'.
    # Both are roots; insertion order wins.
    assert [sp.skillpath_id for sp in ordered] == ["b", "c"]


def test_toposort_handles_cycles_without_dropping_nodes():
    skillpaths = [
        _make_skillpath("a", ["b"]),
        _make_skillpath("b", ["a"]),
        _make_skillpath("c", []),
    ]
    ordered = _toposort_skillpaths(skillpaths)
    ids = [sp.skillpath_id for sp in ordered]
    # 'c' is the only root and goes first; cycle members appended in insertion order.
    assert ids[0] == "c"
    assert set(ids) == {"a", "b", "c"}


def test_toposort_handles_empty_input():
    assert _toposort_skillpaths([]) == []


def test_generate_content_normalizes_missing_goal(monkeypatch):
    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr(
        "app.main.goal_service.get_goal",
        AsyncMock(side_effect=ValueError("No goal found for user default-user")),
    )

    response = client.post("/v1/roadmaps/roadmap-1/generate-content")
    assert response.status_code == 404
    assert response.json()["detail"].startswith("Goal not found for user")


def _roadmap_full_with_skillpath(
    roadmap_id: str, skillpath_id: str, status: str
) -> RoadmapFull:
    return RoadmapFull(
        roadmap_id=roadmap_id,
        title="Test Roadmap",
        version=1,
        summary="Test roadmap",
        target_outcome="Ship tests",
        assumptions=[],
        milestones=[
            MilestoneWithSkillPaths(
                roadmap_id=roadmap_id,
                milestone_id="m1",
                title="Milestone 1",
                description="Desc",
                objective="Obj",
                estimated_hours=1,
                order_index=1,
                skillpaths=[
                    SkillPathItem(
                        roadmap_id=roadmap_id,
                        skillpath_id=skillpath_id,
                        milestone_id="m1",
                        title="Skillpath 1",
                        description="Desc",
                        estimated_hours=1,
                        status=status,
                    )
                ],
            )
        ],
    )


def test_update_skillpath_status_happy_path(monkeypatch):
    roadmap_id = "roadmap-1"
    skillpath_id = "sp-1"

    update_skillpath = AsyncMock(
        return_value=SkillPathItem(
            roadmap_id=roadmap_id,
            skillpath_id=skillpath_id,
            milestone_id="m1",
            title="Skillpath 1",
            description="Desc",
            estimated_hours=1,
            status="completed",
        )
    )
    refreshed = _roadmap_full_with_skillpath(roadmap_id, skillpath_id, "completed")

    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr("app.main.roadmap_service.update_skillpath", update_skillpath)
    monkeypatch.setattr(
        "app.main.roadmap_service.get_roadmap_full", AsyncMock(return_value=refreshed)
    )

    response = client.post(
        f"/v1/roadmaps/{roadmap_id}/skillpaths/{skillpath_id}/status",
        json={"status": "completed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["roadmap_id"] == roadmap_id
    assert body["milestones"][0]["skillpaths"][0]["status"] == "completed"
    update_skillpath.assert_awaited_once()
    assert update_skillpath.await_args.kwargs == {"status": "completed"}


def test_update_skillpath_status_rejects_invalid_value():
    response = client.post(
        "/v1/roadmaps/roadmap-1/skillpaths/sp-1/status",
        json={"status": "not-a-real-status"},
    )
    # FastAPI/Pydantic returns 422 for body validation failures.
    assert response.status_code == 422


def test_update_skillpath_status_returns_404_when_skillpath_missing(monkeypatch):
    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr(
        "app.main.roadmap_service.update_skillpath",
        AsyncMock(side_effect=ValueError("SkillPath sp-1 not found for user default-user")),
    )

    response = client.post(
        "/v1/roadmaps/roadmap-1/skillpaths/sp-1/status",
        json={"status": "completed"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
