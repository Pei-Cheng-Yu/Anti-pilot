## ADDED Requirements

### Requirement: ROADMAP_PLANNING rerank purpose
The system SHALL add a `MemoryRerankPurpose.ROADMAP_PLANNING` enum value and SHALL extend the rerank advisor prompt guidance to describe selecting notes that shape milestone scoping and skillpath selection.

#### Scenario: New purpose is valid in the rerank schema
- **WHEN** a `MemoryRerankRequest` is built with `purpose=ROADMAP_PLANNING`
- **THEN** it validates and `arerank_memories` accepts it, returning a `MemoryRerankResult` with the same purpose

#### Scenario: Advisor prompt includes planning guidance
- **WHEN** `build_rerank_advisor_prompt` is called with `purpose=ROADMAP_PLANNING`
- **THEN** the prompt instructs the advisor to select notes relevant to scoping the milestone's skillpaths

---

### Requirement: skillpath_worker reranks milestone-scoped memory
After retrieving the milestone `LearningMemoryContext`, `skillpath_worker` SHALL call `arerank_memories` with `purpose=ROADMAP_PLANNING`, `task_context` built from the milestone title and objective, and `candidate_memories=context.relevant_notes`. Only the selected notes SHALL be formatted into `SKILLPATH_PROMPT`.

#### Scenario: Different milestones select different notes
- **WHEN** two milestones with different topics rerank the same candidate pool
- **THEN** each milestone's prompt contains the notes the advisor selected for that milestone, which may differ between milestones

#### Scenario: Selection is applied to the prompt only
- **WHEN** the rerank selects a subset of notes
- **THEN** the formatted memory injected into `SKILLPATH_PROMPT` contains only the selected notes, while `milestone_memory_contexts[milestone_id]` still holds the full retrieved context

#### Scenario: Empty selection falls back to full context
- **WHEN** the rerank returns no selected notes
- **THEN** the worker injects the full retrieved context (behaviour no worse than without rerank)

---

### Requirement: LLM-first rerank with deterministic fallback
The milestone rerank SHALL use the Rerank Advisor when `ENABLE_MEMORY_RERANK_ADVISOR` is set and credentials are available, and SHALL otherwise use the deterministic fallback (first `max_selected` candidates by retrieval order).

#### Scenario: Advisor enabled selects per milestone
- **WHEN** `ENABLE_MEMORY_RERANK_ADVISOR=1` and credentials are present
- **THEN** the Rerank Advisor is invoked and its validated selection is used

#### Scenario: Advisor disabled uses deterministic top-N
- **WHEN** `ENABLE_MEMORY_RERANK_ADVISOR` is not set
- **THEN** the rerank returns the first `max_selected` candidates without invoking the LLM, and the worker still narrows the prompt to that subset

---

### Requirement: Goal-level retrieval is unchanged
The change SHALL NOT add rerank to goal-level retrieval. `retrieve_goal_memory` and the milestone-stage prompts SHALL continue to receive the full `goal_memory_context`.

#### Scenario: Goal generation keeps full breadth
- **WHEN** the planner runs goal-level retrieval
- **THEN** no rerank is applied and `generate_milestone` receives all retrieved goal-level notes
