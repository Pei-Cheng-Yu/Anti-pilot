# Backend Memory-Aware Hints And Rerank Policy

The memory-aware hint path keeps retrieval, pedagogical selection, and learner
feedback as separate steps.

## Flow

1. `generate_memory_aware_hint` receives a `HintRequest` with learner, task,
   submitted code, requested hint level, and concept keys.
2. The service builds a retrieval query from the task prompt, submitted code,
   validation feedback, and concepts.
3. `learning_memory.retrieve_learning_memory` returns the deterministic
   `LearningMemoryContext`.
4. The hint service filters retrieved notes to concept-relevant hint candidates.
5. `memory_rerank_policy.arerank_memories` selects the memories that should
   shape the hint and returns teaching guidance. When
   `ENABLE_MEMORY_RERANK_ADVISOR` is enabled and model credentials are present,
   this path invokes the real memory rerank advisor; otherwise it uses the
   deterministic fallback.
6. The hint service invokes the real hint advisor when
   `ENABLE_MEMORY_HINT_ADVISOR` is enabled and model credentials are present.
   The advisor receives the task context, submitted code, retrieved memory, and
   bounded rerank result.
7. The hint service validates the advisor output and returns a structured
   `HintResponse` with hint text, selected memory IDs, focused concepts, hint
   level, and teaching action metadata. Invalid advisor output falls back to the
   deterministic low-spoiler hint.

## Rerank Policy

The rerank policy receives a bounded candidate set. It does not search the
database itself and it never mutates learner memory.

Supported purposes:

- `hint_generation`
- `code_correction`
- `content_generation`

The real advisor can return structured selections, but selected memory IDs must
come from the bounded candidate set. Invalid schemas, invalid IDs, purpose
mismatch, unavailable credentials, disabled advisor flags, or advisor failure
fall back to deterministic candidate order.

## Teaching Actions

The service can return:

- `normal_hint`
- `quick_recap`
- `contrast_example`
- `quick_recap_then_hint`

Default hints are low-spoiler. A first-level nudge should point toward the
concept or operation to inspect, not return a complete corrected line of code.
If the hint advisor returns complete corrected code for a `nudge` or
`conceptual` hint, the service rejects that output and uses the fallback hint.

## Content Generation Integration

Content generation can opt in through
`build_content_generation_memory_guidance(candidate_memories, task_context=...)`.
This produces selected memory IDs and guidance for prompts without changing the
existing content-generation graph contract.

## Advisor Modules And MCP

DeepAgent-backed memory advisors live in `app.advisors.memory_advisors`:

- `generate_hint_advice`
- `rerank_memory_advice`
- `advise_memory_integrity`

The MCP memory tool layer exposes `generate_memory_aware_hint`, so an agent can
ask for a service-backed hint without calling retrieval, rerank, and hint
generation manually.

## Configuration

Advisor execution is controlled by environment flags:

- `ENABLE_MEMORY_HINT_ADVISOR=1` enables the hint advisor.
- `ENABLE_MEMORY_RERANK_ADVISOR=1` enables the rerank advisor.
- `MEMORY_ADVISOR_MODEL` defaults to `google_genai:gemini-3.1-flash-lite-preview`.

The services still require at least one model credential environment variable:
`GOOGLE_API_KEY`, `GEMINI_API_KEY`, or `GOOGLE_GENAI_API_KEY`. Without these
flags and credentials, deterministic fallback remains the local development and
non-live test behavior.

## LangSmith Smoke Fields

For the gated live smoke test, inspect:

- memory retrieval context and selected memory IDs
- hint advisor request/response
- `hint_level`
- `teaching_action`
- fallback behavior if the advisor violates schema, ID, or low-spoiler rules
