from uuid import uuid4

from app.db.model import ReviewConceptModel
from app.schema.entities import LearningContentItem
from fsrs import Card
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def card_to_review_fields(card: Card) -> dict:
    return {
        "state": card.state.value,
        "due": card.due,
        "stability": card.stability if card.stability is not None else 0.0,
        "difficulty": card.difficulty if card.difficulty is not None else 0.0,
        "updated_at": card.last_review,
    }


def learning_content_review_metadata(content: LearningContentItem) -> dict:
    return {
        "skillpath_id": content.skillpath_id,
        "content_type": content.content_type.value,
        "title": content.title,
        "description": content.description,
    }


async def seed_learning_content_review_cards(
    user_id: str,
    contents: list[LearningContentItem],
    session: AsyncSession,
    reset_content_ids: set[str] | None = None,
) -> None:
    if not contents:
        return

    reset_content_ids = reset_content_ids or set()
    content_ids = [content.content_id for content in contents]
    result = await session.execute(
        select(ReviewConceptModel).where(
            ReviewConceptModel.user_id == user_id,
            ReviewConceptModel.source_type == "skill_path",
            ReviewConceptModel.source_ref_id.in_(content_ids),
        )
    )
    existing_by_ref = {row.source_ref_id: row for row in result.scalars()}

    for content in contents:
        existing = existing_by_ref.get(content.content_id)
        if existing:
            existing.concept_metadata = learning_content_review_metadata(content)
            if content.content_id in reset_content_ids:
                card_fields = card_to_review_fields(Card())
                existing.state = card_fields["state"]
                existing.due = card_fields["due"]
                existing.stability = card_fields["stability"]
                existing.difficulty = card_fields["difficulty"]
                existing.updated_at = card_fields["updated_at"]
                existing.elapsed_days = 0
                existing.scheduled_days = 0
                existing.reps = 0
                existing.lapses = 0
            continue

        card = Card()
        card_fields = card_to_review_fields(card)
        session.add(
            ReviewConceptModel(
                concept_id=str(uuid4()),
                user_id=user_id,
                source_type="skill_path",
                source_ref_id=content.content_id,
                concept_metadata=learning_content_review_metadata(content),
                state=card_fields["state"],
                due=card_fields["due"],
                stability=card_fields["stability"],
                difficulty=card_fields["difficulty"],
                updated_at=card_fields["updated_at"],
                elapsed_days=0,
                scheduled_days=0,
                reps=0,
                lapses=0,
            )
        )
