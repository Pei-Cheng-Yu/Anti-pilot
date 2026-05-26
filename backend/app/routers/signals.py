import json
import uuid
from datetime import datetime, timezone

from app.db.model import ReviewConceptModel
from app.db.session import get_session
from app.langgraph.llm.gemini import get_gemini
from app.routers.reviews import card_to_dict
from fastapi import APIRouter
from fsrs import Card, Rating, Scheduler as FSRS
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

router = APIRouter(prefix="/v1/signals", tags=["signals"])
f = FSRS()
DEFAULT_USER_ID = "default-user"


class StruggleSignal(BaseModel):
    user_id: str = DEFAULT_USER_ID
    roadmap_id: str
    milestone_id: str
    skillpath_id: str
    code_context: str
    diagnostic_message: str
    language: str = "unknown"


@router.post("/struggle")
async def report_struggle(signal: StruggleSignal):
    """
    Receives struggle signals from VS Code, extracts the abstraction via LLM,
    and injects it into the FSRS loop with an 'Again' rating.
    """
    llm = get_gemini()
    sys_msg = SystemMessage(
        content="""You are an expert programming tutor analyzer.
You will receive context about a user struggling with a programming task.
You must extract three explicitly formatted fields:
1. "hint": A socratic, gentle hint for the user (1-2 sentences).
2. "concept_name": A short string identifying the abstract programming concept they are struggling with (e.g. "React useEffect Closures").
3. "misconception": A clear string describing the exact abstract logic trap they fell into.

Return pure JSON with keys: "hint", "concept_name", "misconception". Do not include markdown code block fences."""
    )
    human_msg = HumanMessage(
        content=f"Context:\n{signal.code_context}\n\nDiagnostics:\n{signal.diagnostic_message}"
    )
    res = llm.invoke([sys_msg, human_msg])

    try:
        clean_json = res.content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
    except Exception:
        data = {
            "hint": "Take a moment to review the diagnostic warnings carefully.",
            "concept_name": "General Debugging",
            "misconception": "Syntax error or logical gap.",
        }

    card = Card()
    now = datetime.now(timezone.utc)
    updated_card, _ = f.review_card(card, Rating(1), now)
    update_data = card_to_dict(updated_card)

    row = ReviewConceptModel(
        concept_id=str(uuid.uuid4()),
        user_id=signal.user_id,
        source_type="struggle_signal",
        source_ref_id=signal.skillpath_id,
        concept_metadata={
            "roadmap_id": signal.roadmap_id,
            "milestone_id": signal.milestone_id,
            "concept_name": data["concept_name"],
            "misconception": data["misconception"],
            "language": signal.language,
        },
        state=update_data["state"],
        due=update_data["due"],
        stability=update_data["stability"],
        difficulty=update_data["difficulty"],
        updated_at=update_data["updated_at"],
        elapsed_days=0,
        scheduled_days=0,
        reps=1,
        lapses=1,
    )

    async with get_session() as session:
        session.add(row)
        await session.commit()

    return {
        "hint": data["hint"],
        "concept_name": data.get("concept_name", "Unknown Concept"),
        "action_required": True,
    }
