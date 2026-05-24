from app.db.session import get_session
from app.schema.entities import (
    AddMemoryNoteInput,
    CodingProblemAttempt,
    LearnerMemoryNote,
    LearningMemoryContext,
    RecordAndConsolidateAttemptResult,
    RecordCodingProblemAttemptInput,
    RetrieveLearningMemoryInput,
    SkillMasteryState,
    UpdateMemoryNoteInput,
)
from app.services import learning_memory as service
from fastmcp import FastMCP

learning_memory_mcp = FastMCP("learning_memory")


@learning_memory_mcp.tool()
async def add_memory_note(note: AddMemoryNoteInput) -> LearnerMemoryNote:
    """
    Create a durable learner memory note.
    Use this for explicit background facts, manually curated error patterns, or
    agent-authored teaching guidance that should be stored long-term.
    """
    async with get_session() as session:
        return await service.add_memory_note(note, session)


@learning_memory_mcp.tool()
async def update_memory_note(
    user_id: str, update: UpdateMemoryNoteInput
) -> LearnerMemoryNote:
    """
    Patch a learner memory note in place.
    Use this when an existing memory needs refined wording, stronger evidence,
    updated linked concepts, or a lifecycle status change.
    """
    async with get_session() as session:
        return await service.update_memory_note(update, session, user_id=user_id)


@learning_memory_mcp.tool()
async def resolve_memory_note(user_id: str, memory_id: str) -> LearnerMemoryNote:
    """
    Mark a learner memory note as resolved so it stops appearing in default retrieval.
    Use this when repeated evidence shows the learner has moved past an older issue.
    """
    async with get_session() as session:
        return await service.resolve_memory_note(memory_id, session, user_id=user_id)


@learning_memory_mcp.tool()
async def delete_memory_note(user_id: str, memory_id: str) -> str:
    """
    Permanently delete a learner memory note.
    Use this sparingly for bad data, duplicates, or notes created in error.
    """
    async with get_session() as session:
        await service.delete_memory_note(memory_id, session, user_id=user_id)
    return f"Deleted memory note {memory_id}."


@learning_memory_mcp.tool()
async def record_coding_problem_attempt(
    attempt: RecordCodingProblemAttemptInput,
) -> CodingProblemAttempt:
    """
    Persist one coding problem attempt and update mastery state for its skillpath.
    Use this when an evaluator already has feedback, detected concepts, and
    correctness information ready to store.
    """
    async with get_session() as session:
        return await service.record_coding_problem_attempt(attempt, session)


@learning_memory_mcp.tool()
async def record_and_consolidate_attempt(
    attempt: RecordCodingProblemAttemptInput,
) -> RecordAndConsolidateAttemptResult:
    """
    Persist one coding problem attempt, update mastery, and consolidate the result
    into durable memory notes such as error patterns, mastery signals, and teaching heuristics.
    """
    async with get_session() as session:
        saved_attempt, updated_notes = await service.record_and_consolidate_attempt(
            attempt, session
        )
    return RecordAndConsolidateAttemptResult(
        attempt=saved_attempt, updated_notes=updated_notes
    )


@learning_memory_mcp.tool()
async def get_skill_mastery_state(
    user_id: str, skillpath_id: str
) -> SkillMasteryState | None:
    """
    Fetch the current mastery state for one learner and skillpath.
    Use this when an agent wants a quick progress snapshot without a broader memory retrieval.
    """
    async with get_session() as session:
        return await service.get_skill_mastery_state(user_id, skillpath_id, session)


@learning_memory_mcp.tool()
async def retrieve_learning_memory(
    query: RetrieveLearningMemoryInput,
) -> LearningMemoryContext:
    """
    Retrieve learner memory context for a fuzzy teaching or code-correction query.
    Returns mastery state, recent attempts, and ranked memory notes grouped by purpose.
    """
    async with get_session() as session:
        return await service.retrieve_learning_memory(query, session)
