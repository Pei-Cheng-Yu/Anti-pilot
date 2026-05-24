# Support Structured Output and Pgvector Memory Retrieval

## Summary

Replace brittle JSON-text agent responses with typed structured output contracts where the installed agent runtimes support them, keep explicit compatibility fallbacks only at integration boundaries, and upgrade learner-memory retrieval from "fetch every note, score in Python" to Postgres-backed hybrid candidate retrieval using pgvector, full-text search, scope/concept matching, and a small Python rerank.

## Motivation

The current validator and content generator rely on natural-language instructions to emit JSON. That makes the flow fragile when model output includes markdown, extra text, or schema drift. The validator also still assumes sandbox execution as the main evidence source, but the paid cloud sandbox decision is deferred; for now validation should reason over submitted code plus compile/runtime/test evidence supplied from VS Code or another caller.

Learning memory already has the right lifecycle shape: `CodingProblemAttempt -> consolidation -> LearnerMemoryNote -> LearningMemoryContext -> agents`. The missing piece is scalable retrieval. `LearnerMemoryNoteModel.embedding` is JSONB today, and `retrieve_learning_memory` fetches all active notes for the user before Python scoring. The target should let the database retrieve strong candidates first, then let Python or an optional reranker rank a small merged set.

## Goals

- Make code validation prefer `CodeValidationResult` structured output from Deep Agents.
- Make content generation prefer `AdkContentGenerationOutput` structured output when Google ADK supports it.
- Preserve JSON parsing as a named compatibility fallback, not the default contract.
- Stop depending on sandbox execution for validation in this phase.
- Extend validation request data so VS Code compile/runtime/stdout/stderr/test evidence can flow into validation and correction.
- Store learner memory embeddings in real pgvector columns.
- Add Postgres full-text retrieval over learner memory note text.
- Retrieve candidates through vector, keyword, and concept/scope paths before reranking.
- Continue returning the existing structured `LearningMemoryContext` grouped into mastery state, recent attempts, active error patterns, mastery signals, teaching heuristics, background notes, and relevant notes.
- Pass retrieved memory context into correction, content generation, and search/resource recommendation surfaces where the agent has enough user and skillpath context.

## Non-Goals

- Do not add a paid or online sandbox integration in this change.
- Do not remove JSON fallback parsing until all deployed model runtimes are confirmed to support structured outputs.
- Do not replace the existing consolidation lifecycle; improve its storage/retrieval foundation.
- Do not require an LLM reranker in the first implementation. Leave a clean hook for it.

## Target Architecture

```text
CodingProblemAttempt
        ↓
Consolidation
        ↓
LearnerMemoryNote
        ↓
Hybrid Retriever
        ↓
LearningMemoryContext
        ↓
Correction Agent / Content Generator / Search Agent
```

## Target Retrieval Flow

```text
query_text + concept_keys + skillpath_id
        ↓
embed query_text
        ↓
pgvector top 50 semantic candidates
+
full-text top 50 keyword candidates
+
concept/skillpath matched candidates
        ↓
merge + deduplicate
        ↓
hybrid rerank
        ↓
optional LLM/reranker top 5
        ↓
LearningMemoryContext
```

## Success Criteria

- Validator tests show `structured_response` is preferred over JSON-message parsing.
- Content generator tests show typed model instances and dicts can be coerced without JSON text.
- Validation/correction tests show VS Code supplied execution evidence is preserved.
- Database model and migration enable `vector` extension and use a pgvector column for memory embeddings.
- Retriever tests cover candidate merging/deduplication and SQL query construction for vector, full-text, and scope candidate paths.
- `retrieve_learning_memory` no longer fetches all active notes before scoring.
- Content generation can receive `LearningMemoryContext` when user context is available.
