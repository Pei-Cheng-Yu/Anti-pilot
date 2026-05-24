# Design

## Current State

The backend already has Pydantic models for validation, content generation, coding attempts, learner memory notes, mastery state, and `LearningMemoryContext`. `learning_memory.py` handles raw attempt storage, consolidation into `ERROR_PATTERN`, `MASTERY_SIGNAL`, and `HEURISTIC` notes, and final context assembly.

The main gaps are:

- Deep Agent validator prompts demand JSON and parse messages after invocation.
- ADK content generator prompts demand JSON and parse final text.
- `CodeValidationRequest` lacks direct caller-supplied execution evidence fields except problem metadata and submitted code.
- `LearnerMemoryNoteModel.embedding` is `JSONB`, so pgvector search is unavailable.
- Retrieval fetches all active user notes, then scores everything in Python.

## Structured Agent Output

### Validator

`create_code_validator_agent` should pass `response_format=CodeValidationResult` to `create_deep_agent`. `validate_code_submission` should first read `result["structured_response"]` and validate it with `CodeValidationResult.model_validate`. The existing JSON payload extraction should remain below that path as compatibility fallback.

The validator prompt should shift from "run code in a sandbox" to "use submitted code and provided execution evidence." It should explicitly state that no sandbox is assumed for this phase and that missing execution evidence lowers confidence.

### Content Generator

The content generator should introduce a coercion helper:

- `AdkContentGenerationOutput` instance: return as-is.
- `dict`: `model_validate`.
- `str`: extract and validate JSON fallback.

The ADK `Agent` construction should use `output_schema=AdkContentGenerationOutput` only when the configured model supports `output_schema` together with tools. ADK documents this as model-dependent, with Gemini 3-class models supporting the path. The grounded content generator uses `google_search`, so non-Gemini-3 models should keep tools enabled and rely on final JSON text plus Pydantic coercion. Prompt wording should say output must match `AdkContentGenerationOutput`, with JSON-only wording kept as the compatibility contract for tool-enabled runtimes.

## External Execution Evidence

`CodeValidationRequest` should include optional caller-supplied evidence:

- `compile_error`
- `runtime_error`
- `stdout`
- `stderr`
- `test_results`

`CodeValidationResult` already carries most of these fields. Correction should get a small helper that builds a `CodeCorrectionRequest` from the validation result so detected correctness, concepts, mistakes, compile/runtime errors, and test results remain one continuous evidence chain.

## Memory Storage

Use `pgvector.sqlalchemy.Vector` for `LearnerMemoryNoteModel.embedding`. The initial dimension should match the configured production embedding model. If the embedding model is Gemini and returns 3072 dimensions, use `Vector(3072)`.

Add a durable `search_text` column on `learner_memory_notes`, populated from title, summary, tags, linked concepts, linked skillpaths, linked content ids, and evidence attempt ids. Populate it whenever creating or updating a memory note or consolidating an attempt into an existing note.

Migration responsibilities:

- `CREATE EXTENSION IF NOT EXISTS vector`
- Add `search_text`
- Convert `embedding` to `vector(3072)` where possible
- Add an ivfflat or hnsw cosine index for `embedding`
- Add a GIN full-text index over `to_tsvector('english', search_text)`
- Add GIN indexes for concept and scope arrays

If existing JSONB embeddings cannot be cast safely, the migration should preserve rows and set invalid embeddings to `NULL`, then allow normal note update/consolidation to regenerate embeddings.

## Hybrid Retrieval Service

Create `backend/app/services/learning_memory_retriever.py` to isolate candidate retrieval from note CRUD, consolidation, and final context assembly.

The retriever should expose:

- `_get_vector_candidates(payload, query_embedding, session, limit=50)`
- `_get_keyword_candidates(payload, session, limit=50)`
- `_get_scope_candidates(payload, session, limit=50)`
- `_dedupe_note_rows_by_id(rows)`
- `get_memory_note_candidates(payload, query_embedding, session, candidate_limit=50)`

Candidate retrieval should always filter by `user_id` and exclude resolved notes. Optional memory type filtering can either happen in SQL or immediately after candidate merge; SQL is preferred once helper signatures are stable.

Vector query should order by cosine distance:

```python
LearnerMemoryNoteModel.embedding.cosine_distance(query_embedding)
```

Keyword query should use Postgres full-text search:

```sql
to_tsvector('english', search_text) @@ plainto_tsquery('english', :query)
```

Scope query should match any supplied `skillpath_id`, `content_id`, or `concept_keys` against the linked arrays.

After merging and deduplication, `retrieve_learning_memory` should keep the existing `_memory_note_score` rerank so salience, semantic similarity, keyword overlap, concept overlap, and scope boosts still produce explainable final ordering. The difference is that rerank now runs over a small candidate set, not every note.

## Context Use In Agents

Correction already retrieves `LearningMemoryContext`; preserve that path while ensuring validation evidence is recorded before consolidation.

Content generation should add an optional `learning_memory_context` field to `AdkContentGenerationRequest`. The graph node that invokes content generation should retrieve memory when user id and skillpath/concept context are available, and include the serialized context in the prompt only when present.

Search/resource recommendation should use the same retrieval service contract when that surface is implemented or wired. It should receive grouped memory rather than raw note rows.

## Testing Strategy

Use focused unit tests before implementation changes:

- Validator structured response preference.
- Validator fallback remains available for JSON strings.
- Content generator coercion accepts model instance, dict, and JSON string.
- Correction request builder preserves validation evidence.
- Retriever deduplication preserves first-seen order.
- Retriever SQL helpers are exercised with async session fakes or a pgvector-enabled integration database.
- Learning memory service delegates candidate retrieval and still returns grouped `LearningMemoryContext`.

Database tests should be split so pure Python behavior can run without Postgres, while pgvector/full-text integration tests can be marked or configured for a pgvector-enabled database.
