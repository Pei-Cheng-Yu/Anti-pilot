from datetime import datetime, timezone
from typing import Any, Dict, List, Literal

from app.db.model import ReviewConceptModel
from app.db.session import get_session
from app.langgraph.llm.gemini import get_gemini
from app.services.review import card_to_review_fields
from fastapi import APIRouter, HTTPException, Query
from fsrs import Card, Rating, Scheduler as FSRS, State
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from sqlalchemy import select

router = APIRouter(prefix="/v1/reviews", tags=["reviews"])
f = FSRS()
DEFAULT_USER_ID = "default-user"


class ReviewConcept(BaseModel):
    concept_id: str
    user_id: str
    source_type: Literal["struggle_signal", "skill_path"]
    source_ref_id: str
    concept_metadata: Dict[str, Any]
    state: int
    due: str
    stability: float
    difficulty: float
    elapsed_days: int
    scheduled_days: int
    reps: int
    lapses: int


class ReviewGradeRequest(BaseModel):
    grade: Literal[1, 2, 3, 4]


class TaskGenerationResponse(BaseModel):
    task_type: str
    content: str
    solution: str


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def review_row_to_dict(row: ReviewConceptModel) -> dict:
    return {
        "concept_id": row.concept_id,
        "user_id": row.user_id,
        "source_type": row.source_type,
        "source_ref_id": row.source_ref_id,
        "concept_metadata": row.concept_metadata,
        "state": row.state,
        "due": row.due.isoformat(),
        "stability": row.stability,
        "difficulty": row.difficulty,
        "elapsed_days": row.elapsed_days,
        "scheduled_days": row.scheduled_days,
        "reps": row.reps,
        "lapses": row.lapses,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def dict_to_card(row: dict) -> Card:
    state_val = row["state"]
    if state_val == 0:
        state_val = 1

    return Card(
        state=State(state_val),
        due=_parse_datetime(row["due"]),
        stability=row["stability"] if row["stability"] != 0.0 else None,
        difficulty=row["difficulty"] if row["difficulty"] != 0.0 else None,
        last_review=_parse_datetime(row.get("updated_at")),
    )


def card_to_dict(card: Card) -> dict:
    return card_to_review_fields(card)


@router.get("/", response_model=List[ReviewConcept])
async def get_all_reviews(user_id: str = Query(default=DEFAULT_USER_ID)):
    try:
        async with get_session() as session:
            result = await session.execute(
                select(ReviewConceptModel).where(ReviewConceptModel.user_id == user_id)
            )
            return [review_row_to_dict(row) for row in result.scalars()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/due", response_model=List[ReviewConcept])
async def get_due_reviews(user_id: str = Query(default=DEFAULT_USER_ID)):
    try:
        async with get_session() as session:
            now = datetime.now(timezone.utc)
            result = await session.execute(
                select(ReviewConceptModel).where(
                    ReviewConceptModel.user_id == user_id,
                    ReviewConceptModel.due <= now,
                )
            )
            return [review_row_to_dict(row) for row in result.scalars()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{concept_id}/generate-task", response_model=TaskGenerationResponse)
async def generate_task_for_concept(
    concept_id: str, user_id: str = Query(default=DEFAULT_USER_ID)
):
    async with get_session() as session:
        result = await session.execute(
            select(ReviewConceptModel).where(
                ReviewConceptModel.concept_id == concept_id,
                ReviewConceptModel.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Review concept not found")

    metadata = row.concept_metadata or {}

    try:
        system_msg = SystemMessage(
            content="""You are an expert programming tutor.
Your goal is to generate a 'tiny coding problem' (e.g., a debugging snippet, fill-in-the-blank, or short refactor) to test the user's understanding of a specific programming concept.
If a "misconception" is provided, you MUST design the problem specifically around testing if they still hold that misconception. Do not use the user's original code; invent a clean, minimal "toy problem" that purely tests the abstract logical trap.
Return the output in Markdown format, with headers ### Task and ### Solution. Do not include extra conversational text."""
        )
        human_msg = HumanMessage(
            content=f"Concept Metadata:\n{metadata}\n\nGenerate a tiny coding test specifically targeting the underlying concept and any misconception present."
        )
        output_content = get_gemini().invoke([system_msg, human_msg]).content
        parts = output_content.split("### Solution")
        task_content = parts[0].replace("### Task", "").strip()
        solution_content = parts[1].strip() if len(parts) > 1 else "Solution not provided."
        return TaskGenerationResponse(
            task_type="coding_snippet",
            content=task_content,
            solution=solution_content,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{concept_id}/grade")
async def grade_review(
    concept_id: str,
    request: ReviewGradeRequest,
    user_id: str = Query(default=DEFAULT_USER_ID),
):
    async with get_session() as session:
        result = await session.execute(
            select(ReviewConceptModel).where(
                ReviewConceptModel.concept_id == concept_id,
                ReviewConceptModel.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Review concept not found")

        row_data = review_row_to_dict(row)
        card = dict_to_card(row_data)
        now = datetime.now(timezone.utc)
        updated_card, _ = f.review_card(card, Rating(request.grade), now)

        update_data = card_to_dict(updated_card)
        row.state = update_data["state"]
        row.due = update_data["due"]
        row.stability = update_data["stability"]
        row.difficulty = update_data["difficulty"]
        row.updated_at = update_data["updated_at"]
        row.elapsed_days = (now - card.last_review).days if card.last_review else 0
        row.scheduled_days = (updated_card.due - now).days
        row.reps += 1
        row.lapses += 1 if request.grade == 1 else 0

        await session.commit()
        return review_row_to_dict(row)
