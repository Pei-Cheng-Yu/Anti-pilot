# Structured Output and Learning Memory Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace brittle JSON-text parsing with structured output where the agent frameworks support it, simplify validation to consume VS Code execution signals for now, and upgrade learning-memory retrieval to real Postgres candidate search with pgvector plus full-text search.

**Architecture:** Keep the existing memory lifecycle intact: `CodingProblemAttempt -> consolidation -> LearnerMemoryNote -> Hybrid Retriever -> LearningMemoryContext -> agents`. Agent output contracts become typed Pydantic schemas first, with JSON-text parsing only as an explicit compatibility fallback. Memory retrieval moves from fetching all user notes into Python to fetching candidate pools in Postgres, then reranking a small merged set in Python.

**Tech Stack:** Python 3.12, Pydantic v2, Deep Agents, Google ADK, SQLAlchemy async, asyncpg, PostgreSQL, pgvector, PostgreSQL full-text search, pytest.

---

## File Structure

- Modify `backend/app/validators/deepagent_validator.py`: use Deep Agents `response_format=CodeValidationResult`; remove sandbox-only assumptions from the prompt; keep fallback JSON parser behind a small helper.
- Modify `backend/app/validators/schemas.py`: keep `CodeValidationRequest` and `CodeValidationResult`, add fields for external VS Code execution signals if needed.
- Modify `backend/app/adk_agents/content_generator/agent.py`: move toward ADK structured output if supported by installed ADK; otherwise isolate JSON fallback in a named compatibility path.
- Modify `backend/app/adk_agents/content_generator/prompts.py`: remove JSON-only wording once structured output is active.
- Modify `backend/app/services/code_correction.py`: accept validator/VS Code supplied compile/runtime/test evidence directly and preserve current memory persistence path.
- Modify `backend/app/db/model.py`: switch `LearnerMemoryNoteModel.embedding` from `JSONB` to a pgvector column and add full-text search support.
- Modify `requirements.txt`: add `pgvector` Python package.
- Modify `docker-compose.yml`: use a Postgres image with pgvector support or install the extension in DB initialization.
- Create `backend/app/services/learning_memory_retriever.py`: isolate candidate retrieval and reranking from memory CRUD/consolidation.
- Modify `backend/app/services/learning_memory.py`: delegate retrieval to `learning_memory_retriever.py`.
- Create migration under the repo migration location once Alembic layout is confirmed: enable `vector`, add vector/full-text columns and indexes.
- Add tests:
  - `backend/tests/test_deepagent_validator.py`
  - `backend/tests/test_content_generator_agent.py`
  - `backend/tests/test_code_correction_service.py`
  - `backend/tests/test_learning_memory_retriever.py`

---

### Task 1: Lock Current Tests Before Refactor

**Files:**
- Test: `backend/tests/test_learning_memory_service.py`
- Test: `backend/tests/test_code_correction_service.py`

- [ ] **Step 1: Run current memory and correction tests**

Run from `backend/`:

```bash
PYTHONPATH=. python -m pytest tests/test_learning_memory_service.py tests/test_code_correction_service.py -q
```

Expected: all tests pass before refactoring begins. If a test fails because the database is missing new tables, run the suite after applying the existing SQLAlchemy metadata setup used by the tests.

- [ ] **Step 2: Record current failure if not green**

If tests fail, capture the failing test names and first traceback line in the implementation notes before changing code. Fix test setup issues before touching structured-output or retrieval code.

- [ ] **Step 3: Commit baseline if green**

```bash
git add backend/tests/test_learning_memory_service.py backend/tests/test_code_correction_service.py backend/app/services backend/app/schema backend/app/db backend/app/mcp
git commit -m "test: lock learning memory correction baseline"
```

Expected: commit succeeds or reports there is nothing staged if the baseline was already committed.

---

### Task 2: Structured Output for Deep Agent Validator

**Files:**
- Modify: `backend/app/validators/deepagent_validator.py`
- Modify: `backend/app/validators/schemas.py`
- Test: `backend/tests/test_deepagent_validator.py`

- [ ] **Step 1: Write tests for structured result extraction**

Create `backend/tests/test_deepagent_validator.py`:

```python
import pytest

from app.schema.enums import AttemptCorrectness
from app.validators.deepagent_validator import validate_code_submission
from app.validators.schemas import CodeValidationRequest, CodeValidationResult


class FakeStructuredAgent:
    async def ainvoke(self, _payload):
        return {
            "structured_response": CodeValidationResult(
                correctness=AttemptCorrectness.CORRECT,
                has_serious_blocker=False,
                validation_strategy="reasoned_from_external_execution",
                feedback_summary="The submitted code matches the requested behavior.",
                confidence_score=0.86,
            )
        }


@pytest.mark.asyncio
async def test_validate_code_submission_prefers_structured_response(monkeypatch):
    monkeypatch.setattr(
        "app.validators.deepagent_validator.create_code_validator_agent",
        lambda **_kwargs: FakeStructuredAgent(),
    )

    result = await validate_code_submission(
        CodeValidationRequest(
            user_id="user-1",
            skillpath_id="sp-1",
            content_id="cp-1",
            language="python",
            coding_problem_prompt="Return the sum of two numbers.",
            submitted_code="def add(a, b): return a + b",
        ),
        backend=object(),
    )

    assert result.correctness == AttemptCorrectness.CORRECT
    assert result.validation_strategy == "reasoned_from_external_execution"
```

- [ ] **Step 2: Run the new test and verify it fails**

Run from `backend/`:

```bash
PYTHONPATH=. python -m pytest tests/test_deepagent_validator.py -q
```

Expected: FAIL because `validate_code_submission` does not yet read `structured_response`.

- [ ] **Step 3: Update validator agent creation**

In `backend/app/validators/deepagent_validator.py`, change `create_code_validator_agent` to pass `response_format=CodeValidationResult`:

```python
def create_code_validator_agent(*, backend: Any | None = None, model: str | None = None):
    kwargs: dict[str, Any] = {
        "model": model or CODE_VALIDATOR_MODEL,
        "system_prompt": _VALIDATOR_SYSTEM_PROMPT,
        "response_format": CodeValidationResult,
    }
    if backend is not None:
        kwargs["backend"] = backend
    return create_deep_agent(**kwargs)
```

- [ ] **Step 4: Update validator prompt for no-sandbox v1**

Replace `_VALIDATOR_SYSTEM_PROMPT` with:

```python
_VALIDATOR_SYSTEM_PROMPT = """You are a code validation agent.

Your job is to judge a learner-submitted solution for one coding problem.

For this version, do not assume sandbox execution is available. Use the submitted code, coding problem prompt, and any external compile/runtime/test evidence supplied by the caller.

Validation process:
1. Read the coding problem carefully.
2. Inspect the submitted code for serious blockers such as syntax issues, missing required structure, or clear mismatch with the prompt.
3. Use provided compile_error, runtime_error, stdout, stderr, and test_results as execution evidence when present.
4. If execution evidence is missing, reason from the code and lower confidence_score.
5. Return a structured CodeValidationResult.

Important rules:
- Prefer provided execution evidence over pure reasoning.
- Do not invent tests that were not provided or run.
- Use validation_strategy values such as external_execution_evidence, reason_only_blocker, or reasoned_static_review.
- detected_mistakes should be compact reusable labels like missing_await or wrong_return_shape.
"""
```

- [ ] **Step 5: Read structured output first, keep fallback**

In `validate_code_submission`, check `result.get("structured_response")` before parsing messages:

```python
structured_response = result.get("structured_response")
if structured_response is not None:
    return CodeValidationResult.model_validate(structured_response)
```

Keep the existing JSON parser below this block as a fallback for providers that do not emit `structured_response`.

- [ ] **Step 6: Run validator tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_deepagent_validator.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/validators/deepagent_validator.py backend/app/validators/schemas.py backend/tests/test_deepagent_validator.py
git commit -m "feat: use structured output for code validator"
```

---

### Task 3: Extend Validation Request for VS Code Evidence

**Files:**
- Modify: `backend/app/validators/schemas.py`
- Modify: `backend/app/services/code_correction.py`
- Test: `backend/tests/test_code_correction_service.py`

- [ ] **Step 1: Add external execution fields**

In `CodeValidationRequest`, add:

```python
compile_error: str | None = Field(default=None)
runtime_error: str | None = Field(default=None)
stdout: str | None = Field(default=None)
stderr: str | None = Field(default=None)
```

- [ ] **Step 2: Add a mapping helper from validation to correction**

In `backend/app/services/code_correction.py`, add:

```python
from app.validators.schemas import CodeValidationResult


def build_correction_request_from_validation(
    *,
    user_id: str,
    skillpath_id: str,
    content_id: str,
    coding_problem_prompt: str,
    submitted_code: str,
    language: str,
    validation: CodeValidationResult,
) -> CodeCorrectionRequest:
    return CodeCorrectionRequest(
        user_id=user_id,
        skillpath_id=skillpath_id,
        content_id=content_id,
        coding_problem_prompt=coding_problem_prompt,
        submitted_code=submitted_code,
        language=language,
        compile_error=validation.compile_error,
        runtime_error=validation.runtime_error,
        test_results=validation.test_results,
        correctness=validation.correctness,
        feedback_summary=validation.feedback_summary,
        detected_concepts=validation.detected_concepts,
        detected_mistakes=validation.detected_mistakes,
    )
```

- [ ] **Step 3: Write test for mapping**

Append to `backend/tests/test_code_correction_service.py`:

```python
from app.validators.schemas import CodeValidationResult


def test_build_correction_request_from_validation():
    validation = CodeValidationResult(
        correctness=AttemptCorrectness.RUNTIME_ERROR,
        has_serious_blocker=True,
        blocker_reason="Runtime error from VS Code run",
        runtime_error="NameError: name 'x' is not defined",
        validation_strategy="external_execution_evidence",
        feedback_summary="The code fails because x is undefined.",
        detected_concepts=["python.variables"],
        detected_mistakes=["undefined variable"],
        confidence_score=0.91,
    )

    request = code_correction_service.build_correction_request_from_validation(
        user_id="user-1",
        skillpath_id="sp-1",
        content_id="cp-1",
        coding_problem_prompt="Print x.",
        submitted_code="print(x)",
        language="python",
        validation=validation,
    )

    assert request.runtime_error == "NameError: name 'x' is not defined"
    assert request.correctness == AttemptCorrectness.RUNTIME_ERROR
    assert request.detected_mistakes == ["undefined variable"]
```

- [ ] **Step 4: Run correction tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_code_correction_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/validators/schemas.py backend/app/services/code_correction.py backend/tests/test_code_correction_service.py
git commit -m "feat: map external validation evidence into correction flow"
```

---

### Task 4: Structured Output for Content Generator

**Files:**
- Modify: `backend/app/adk_agents/content_generator/agent.py`
- Modify: `backend/app/adk_agents/content_generator/prompts.py`
- Test: `backend/tests/test_content_generator_agent.py`

- [ ] **Step 1: Write a test for direct structured result extraction**

Create `backend/tests/test_content_generator_agent.py`:

```python
from app.adk_agents.content_generator.agent import _coerce_content_generation_output
from app.adk_agents.content_generator.schemas import (
    AdkArticleOutput,
    AdkContentGenerationOutput,
    AdkCodingProblemOutput,
)


def test_coerce_content_generation_output_accepts_model_instance():
    output = AdkContentGenerationOutput(
        article=AdkArticleOutput(
            title="Read FastAPI routing",
            description="Learn route handlers.",
            skill_intro="Routes connect URLs to Python functions.",
            reading_content="FastAPI routes are declared with decorators.",
            references=[],
            source_notes=[],
        ),
        coding_problem=AdkCodingProblemOutput(
            title="Write a route",
            description="Practice defining a route.",
            prompt="Create a GET /health route.",
            difficulty="easy",
        ),
    )

    assert _coerce_content_generation_output(output).article.title == "Read FastAPI routing"
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_content_generator_agent.py -q
```

Expected: FAIL because `_coerce_content_generation_output` does not exist yet.

- [ ] **Step 3: Add coercion helper**

In `backend/app/adk_agents/content_generator/agent.py`, add:

```python
def _coerce_content_generation_output(value) -> AdkContentGenerationOutput:
    if isinstance(value, AdkContentGenerationOutput):
        return value
    if isinstance(value, dict):
        return AdkContentGenerationOutput.model_validate(value)
    if isinstance(value, str):
        return AdkContentGenerationOutput.model_validate_json(
            _extract_json_payload(value)
        )
    raise TypeError(f"Unsupported content generation output type: {type(value)!r}")
```

- [ ] **Step 4: Try ADK output_schema if the installed ADK supports it**

In `_build_agent`, update the `Agent(...)` construction:

```python
agent_kwargs = {
    "name": "content_generator",
    "model": CONTENT_GENERATOR_MODEL,
    "instruction": CONTENT_GENERATOR_INSTRUCTION,
    "tools": [google_search],
}
try:
    agent_kwargs["output_schema"] = AdkContentGenerationOutput
    return Agent(**agent_kwargs)
except TypeError:
    agent_kwargs.pop("output_schema", None)
    return Agent(**agent_kwargs)
```

This keeps compatibility with ADK versions that do not accept `output_schema`.

- [ ] **Step 5: Use coercion at final parse point**

Replace:

```python
return AdkContentGenerationOutput.model_validate_json(
    _extract_json_payload(final_response_text)
)
```

with:

```python
return _coerce_content_generation_output(final_response_text)
```

- [ ] **Step 6: Soften JSON-only prompt wording**

In `backend/app/adk_agents/content_generator/prompts.py`, replace instructions like `Return JSON only` with wording that says the output must match `AdkContentGenerationOutput`. Keep one compatibility line: `If the runtime asks for plain text, emit a single JSON object matching the schema.`

- [ ] **Step 7: Run content generator unit test**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_content_generator_agent.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/adk_agents/content_generator/agent.py backend/app/adk_agents/content_generator/prompts.py backend/tests/test_content_generator_agent.py
git commit -m "feat: prefer structured content generation output"
```

---

### Task 5: Add pgvector Dependency and DB Support

**Files:**
- Modify: `requirements.txt`
- Modify: `docker-compose.yml`
- Modify: `backend/app/db/model.py`
- Create: migration file under the repo migration directory after confirming Alembic location

- [ ] **Step 1: Add Python pgvector package**

In `requirements.txt`, add:

```txt
pgvector==0.4.1
```

- [ ] **Step 2: Use vector column in model**

In `backend/app/db/model.py`, import:

```python
from pgvector.sqlalchemy import Vector
```

Change:

```python
embedding: Mapped[list[float] | None] = mapped_column(JSONB)
```

to:

```python
embedding: Mapped[list[float] | None] = mapped_column(Vector(3072))
```

Use `3072` if the configured Gemini embedding model emits 3072 dimensions. If local fake test embeddings use 4 dimensions, tests should avoid DB-level vector search or use a test-only model setup.

- [ ] **Step 3: Add text-search column**

In `LearnerMemoryNoteModel`, add:

```python
search_text: Mapped[str] = mapped_column(Text, default="")
```

This keeps full-text index creation simple in the first migration.

- [ ] **Step 4: Update Docker DB image**

In `docker-compose.yml`, use a pgvector-ready image for Postgres:

```yaml
image: pgvector/pgvector:pg16
```

Keep existing environment and ports unchanged.

- [ ] **Step 5: Add migration operations**

Create a migration that executes:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE learner_memory_notes ADD COLUMN IF NOT EXISTS search_text TEXT NOT NULL DEFAULT '';
ALTER TABLE learner_memory_notes ALTER COLUMN embedding TYPE vector(3072) USING NULL;
CREATE INDEX IF NOT EXISTS ix_learner_memory_notes_embedding
ON learner_memory_notes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS ix_learner_memory_notes_search_text
ON learner_memory_notes USING gin (to_tsvector('english', search_text));
CREATE INDEX IF NOT EXISTS ix_learner_memory_notes_concepts
ON learner_memory_notes USING gin (linked_concepts);
CREATE INDEX IF NOT EXISTS ix_learner_memory_notes_skillpaths
ON learner_memory_notes USING gin (linked_skillpath_ids);
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt docker-compose.yml backend/app/db/model.py
git add backend/*migrations* backend/alembic backend/migrations
git commit -m "feat: add pgvector storage for learner memory"
```

Expected: git stages whichever migration path exists in the repo.

---

### Task 6: Extract Hybrid Retriever Service

**Files:**
- Create: `backend/app/services/learning_memory_retriever.py`
- Modify: `backend/app/services/learning_memory.py`
- Test: `backend/tests/test_learning_memory_retriever.py`

- [ ] **Step 1: Create retriever test for candidate merging**

Create `backend/tests/test_learning_memory_retriever.py` with a focused unit test around a pure helper:

```python
from app.services.learning_memory_retriever import _dedupe_note_rows_by_id


class Row:
    def __init__(self, memory_id):
        self.memory_id = memory_id


def test_dedupe_note_rows_by_id_preserves_first_seen_order():
    rows = [Row("a"), Row("b"), Row("a"), Row("c")]

    result = _dedupe_note_rows_by_id(rows)

    assert [row.memory_id for row in result] == ["a", "b", "c"]
```

- [ ] **Step 2: Implement helper and skeleton**

Create `backend/app/services/learning_memory_retriever.py`:

```python
from __future__ import annotations

from app.db.model import LearnerMemoryNoteModel
from app.schema.entities import RetrieveLearningMemoryInput
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


def _dedupe_note_rows_by_id(
    rows: list[LearnerMemoryNoteModel],
) -> list[LearnerMemoryNoteModel]:
    seen: set[str] = set()
    deduped: list[LearnerMemoryNoteModel] = []
    for row in rows:
        if row.memory_id in seen:
            continue
        seen.add(row.memory_id)
        deduped.append(row)
    return deduped
```

- [ ] **Step 3: Add vector candidate query**

In `learning_memory_retriever.py`, add:

```python
async def _get_vector_candidates(
    payload: RetrieveLearningMemoryInput,
    query_embedding: list[float],
    session: AsyncSession,
    limit: int = 50,
) -> list[LearnerMemoryNoteModel]:
    result = await session.execute(
        select(LearnerMemoryNoteModel)
        .where(LearnerMemoryNoteModel.user_id == payload.user_id)
        .where(LearnerMemoryNoteModel.status != "resolved")
        .where(LearnerMemoryNoteModel.embedding.is_not(None))
        .order_by(LearnerMemoryNoteModel.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    return list(result.scalars())
```

- [ ] **Step 4: Add keyword candidate query**

Add:

```python
async def _get_keyword_candidates(
    payload: RetrieveLearningMemoryInput,
    session: AsyncSession,
    limit: int = 50,
) -> list[LearnerMemoryNoteModel]:
    result = await session.execute(
        select(LearnerMemoryNoteModel)
        .where(LearnerMemoryNoteModel.user_id == payload.user_id)
        .where(LearnerMemoryNoteModel.status != "resolved")
        .where(
            text("to_tsvector('english', search_text) @@ plainto_tsquery('english', :query)")
        )
        .params(query=payload.query_text)
        .limit(limit)
    )
    return list(result.scalars())
```

- [ ] **Step 5: Add concept/scope candidate query**

Add:

```python
async def _get_scope_candidates(
    payload: RetrieveLearningMemoryInput,
    session: AsyncSession,
    limit: int = 50,
) -> list[LearnerMemoryNoteModel]:
    conditions = []
    if payload.skillpath_id:
        conditions.append(LearnerMemoryNoteModel.linked_skillpath_ids.any(payload.skillpath_id))
    if payload.content_id:
        conditions.append(LearnerMemoryNoteModel.linked_content_ids.any(payload.content_id))
    for concept in payload.concept_keys:
        conditions.append(LearnerMemoryNoteModel.linked_concepts.any(concept))
    if not conditions:
        return []
    result = await session.execute(
        select(LearnerMemoryNoteModel)
        .where(LearnerMemoryNoteModel.user_id == payload.user_id)
        .where(LearnerMemoryNoteModel.status != "resolved")
        .where(or_(*conditions))
        .limit(limit)
    )
    return list(result.scalars())
```

Also import `or_` from SQLAlchemy.

- [ ] **Step 6: Add public candidate function**

Add:

```python
async def get_memory_note_candidates(
    payload: RetrieveLearningMemoryInput,
    query_embedding: list[float],
    session: AsyncSession,
    candidate_limit: int = 50,
) -> list[LearnerMemoryNoteModel]:
    vector_rows = await _get_vector_candidates(payload, query_embedding, session, candidate_limit)
    keyword_rows = await _get_keyword_candidates(payload, session, candidate_limit)
    scope_rows = await _get_scope_candidates(payload, session, candidate_limit)
    return _dedupe_note_rows_by_id([*vector_rows, *keyword_rows, *scope_rows])
```

- [ ] **Step 7: Run retriever tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_learning_memory_retriever.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/learning_memory_retriever.py backend/tests/test_learning_memory_retriever.py
git commit -m "feat: add hybrid learning memory candidate retriever"
```

---

### Task 7: Wire Retriever Into Learning Memory Service

**Files:**
- Modify: `backend/app/services/learning_memory.py`
- Test: `backend/tests/test_learning_memory_service.py`

- [ ] **Step 1: Import retriever**

In `backend/app/services/learning_memory.py`, add:

```python
from app.services.learning_memory_retriever import get_memory_note_candidates
```

- [ ] **Step 2: Replace full note fetch in `retrieve_learning_memory`**

Replace the current block that executes `notes_query = select(LearnerMemoryNoteModel)...` with:

```python
note_rows = await get_memory_note_candidates(
    payload,
    query_embedding,
    session,
    candidate_limit=max(50, payload.top_k_notes * 10),
)
if payload.memory_types:
    allowed_types = {memory_type.value for memory_type in payload.memory_types}
    note_rows = [row for row in note_rows if row.memory_type in allowed_types]
```

Move `query_embedding = await _async_embed_text(payload.query_text)` before this call.

- [ ] **Step 3: Keep Python reranking**

Keep the existing `sorted(... _memory_note_score ...)[: payload.top_k_notes]` block so Python reranks only the reduced candidate set.

- [ ] **Step 4: Update MVP comment**

Replace the old comment with:

```python
# Candidate retrieval happens in Postgres; Python keeps the final hybrid rerank
# small and explainable. A future LLM/reranker can operate on this same candidate set.
```

- [ ] **Step 5: Run memory tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_learning_memory_service.py tests/test_learning_memory_retriever.py -q
```

Expected: PASS with a pgvector-enabled test database.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/learning_memory.py backend/app/services/learning_memory_retriever.py backend/tests/test_learning_memory_service.py backend/tests/test_learning_memory_retriever.py
git commit -m "feat: use database candidates for learning memory retrieval"
```

---

### Task 8: Use Learning Memory Context in Content Generation Request

**Files:**
- Modify: `backend/app/adk_agents/content_generator/schemas.py`
- Modify: `backend/app/langgraph/content_generation/graphs/generate_learning_content/nodes.py`
- Modify: `backend/app/adk_agents/content_generator/prompts.py`
- Test: `backend/tests/test_learning_content_generation.py`

- [ ] **Step 1: Add optional memory context to ADK request**

In `AdkContentGenerationRequest`, add:

```python
learning_memory_context: LearningMemoryContext | None = None
```

Import `LearningMemoryContext` from `app.schema.entities`.

- [ ] **Step 2: Retrieve memory in content worker**

In `content_worker`, before constructing `AdkContentGenerationRequest`, retrieve memory with `learning_memory.retrieve_learning_memory(...)` when a user/session is available in graph state. If graph state currently lacks `user_id`, add `user_id: str | None` to `ContentGenerationState` and pass it from the learning director when invoking content generation.

- [ ] **Step 3: Update content prompt**

In `build_content_generation_prompt`, include memory context only when present:

```python
if request.learning_memory_context:
    sections.append(
        "Learner memory context:\n"
        + request.learning_memory_context.model_dump_json(indent=2)
    )
```

- [ ] **Step 4: Add test asserting memory context passes through**

Update `backend/tests/test_learning_content_generation.py` so the fake content generator receives `AdkContentGenerationRequest` and asserts `learning_memory_context` is either populated when `user_id` exists or omitted when no user id exists.

- [ ] **Step 5: Run content generation test**

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_learning_content_generation.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/adk_agents/content_generator/schemas.py backend/app/adk_agents/content_generator/prompts.py backend/app/langgraph/content_generation backend/tests/test_learning_content_generation.py
git commit -m "feat: pass learner memory into content generation"
```

---

## Self-Review

Spec coverage:
- Structured output for validator: Task 2.
- Structured output cleanup for content generator: Task 4.
- No paid cloud sandbox for now; use VS Code supplied compile/runtime/test evidence: Task 3.
- Raw attempt storage, consolidation, memory-note groups: already implemented and protected by Task 1 baseline tests.
- pgvector semantic candidates, full-text candidates, concept/scope candidates, merge/dedupe, Python rerank: Tasks 5-7.
- Structured context for agents: existing `LearningMemoryContext`, reinforced by Task 8 for content generation.

Placeholder scan:
- The plan avoids `TBD`, `TODO`, and vague implementation instructions. The only conditional is the migration location because this repo needs the Alembic path confirmed during implementation; the SQL operations are explicit.

Type consistency:
- `CodeValidationRequest`, `CodeValidationResult`, `RetrieveLearningMemoryInput`, `LearningMemoryContext`, and `LearnerMemoryNoteModel` match the current codebase names.
- `response_format=CodeValidationResult` matches the Deep Agents structured output docs.
- `AdkContentGenerationOutput` remains the content generator output type.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-04-structured-output-memory-retrieval.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints for review.
