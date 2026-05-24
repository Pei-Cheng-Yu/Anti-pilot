# Anti-pilot: A Learner-Memory System for Personalized Agentic Education

Date: 2026-05-07

## Abstract

Modern coding agents have become powerful enough that a beginner can ask them
almost anything and receive a useful answer immediately. This changes the role
of learning software. Traditional learning websites still tend to provide fixed
courses, fixed exercises, and fixed explanations. They are reliable, but often
too slow to adapt to what a learner is actually forgetting, misunderstanding, or
about to struggle with.

Anti-pilot explores a different model: an agentic learning system that remembers
learner behavior, observes coding attempts, retrieves relevant memory at the
right moment, generates a personalized roadmap, reviews that roadmap, and then
produces customized learning content for each skill path. The goal is not only
to answer questions, but to guide the learner based on their personal error
patterns, weak concepts, missing prerequisites, repeated mistakes, saved goals,
learning profile, roadmap context, and likely future forgetting.

This record summarizes the motivation, technical direction, current progress,
ongoing work, and future research plan for the project.

## 1. Introduction

Coding agents are becoming a new kind of learning interface. A beginner no
longer needs to wait for a course author to explain a topic, search through a
forum, or follow a rigid curriculum. They can ask an agent to explain a concept,
debug code, generate practice problems, compare approaches, or build a project
step by step.

However, this power also creates a new problem. If the agent only answers the
current question, it may help in the moment without building long-term
understanding. A learner can receive correct answers while still repeating the
same mistakes. They may forget prerequisite ideas, skip over conceptual gaps, or
depend on the agent too much without noticing what they have not mastered.

Traditional learning websites solve part of this problem by offering structured
paths, quizzes, and exercises. But these systems are usually static. Every
learner receives almost the same sequence, even when their actual weaknesses are
different. The pace of adaptation is slow: the system often cannot react deeply
to a learner's code, execution errors, failed attempts, or remembered mistakes.

Anti-pilot is built around the idea that the learning path itself should become
dynamic. The system should remember what the learner usually forgets, what they
recently failed, what concepts are weak, and what misconceptions are likely to
return. Then it should use that memory to customize hints, exercises, generated
content, roadmap decisions, and learning-director actions.

## 2. Problem Statement

The project focuses on four connected problems.

First, beginner learners need immediate guidance, but immediate answers are not
always the same as learning. A strong coding agent can solve the problem for the
learner, but the learner still needs scaffolding, recall, and personalized
practice.

Second, fixed learning websites are too slow and too general. They cannot easily
change a lesson based on the learner's latest runtime error, repeated missing
`await`, weak understanding of route handlers, or confusion between similar
concepts.

Third, most learning systems do not preserve rich memory. They may store scores
or completed lessons, but they often do not store reusable learning evidence:
error patterns, code-correction history, mastery signals, teaching heuristics,
and concept-level weaknesses.

Fourth, adaptive systems are difficult to trust if their memory path is hidden.
Developers need to inspect why memory was retrieved, what memory entered the
agent prompt, and whether generated content was actually personalized.

## 3. Proposed System

Anti-pilot proposes an agentic learning backend with learner memory as a core
substrate.

The system is organized around a learning director. The learning director uses
saved user data, planner graphs, MCP tools, roadmap review tools, content
generation, and learner memory to coordinate the learning workflow. It can fetch
the learner's saved goal and profile, generate a roadmap, persist it, review and
adjust it, generate learning content for saved skillpaths, and store the result.

The system also records coding attempts and validation evidence, consolidates
repeated behavior into memory notes, retrieves relevant memory during learning
tasks, and injects that context into content-generation and correction agents.
Instead of only asking, "What does the learner want now?", the system also asks:

- What is the learner's saved goal?
- What is their learning profile, schedule, and constraint set?
- What roadmap structure best fits this learner?
- What does this learner usually forget?
- What did this learner recently fail?
- What prerequisite might be missing?
- Which mistakes are repeated enough to become an error pattern?
- Which hint would guide without giving away the whole answer?
- Which learning path should come next for this specific learner?

The long-term research goal is a fully customized learning path. Each learner
should receive content, exercises, hints, and review timing based on their own
goal, profile, roadmap, and memory profile, not only on a static curriculum.

## 4. Technical Contributions

Anti-pilot currently provides several technical mechanisms toward this goal.

### 4.1 Learning Director Orchestration

The learning director is the top-level agent interface for the learning system.
It combines local graph tools with MCP tools for saved backend state.

The current director can:

- fetch saved learner goals and profiles through MCP tools
- run the roadmap planner through `run_planner`
- persist generated roadmaps to the database
- fetch and review the saved roadmap
- update milestones or skillpaths when review finds real issues
- call `run_content_generator` after the roadmap is ready
- persist generated learning content back into the roadmap
- inject `user_id` automatically into managed MCP tool calls

This solves the orchestration problem. A personalized learning system needs more
than isolated agents; it needs a director that knows when to plan, when to
review, when to generate content, and when to use saved user data.

### 4.2 Roadmap Generation and Review

Anti-pilot includes a LangGraph roadmap planner. The planner creates a roadmap
from the learner's goal and learning profile, generates milestones and
skillpaths, and uses review logic to check for structural problems before
downstream content generation.

Roadmap policy prompts guide the planner to consider sequencing, prerequisites,
deadline feasibility, learner strength, overload risk, and milestone coherence.
The roadmap-generation skill then enforces an operational workflow: fetch saved
goal/profile, run the planner, fetch the full roadmap, review it, fix real
issues with roadmap update tools, optionally generate content, and verify that
content exists.

This solves the static-curriculum problem. Instead of giving every learner the
same path, the project can generate a roadmap around the learner's specific
target outcome, background, constraints, and later memory signals.

### 4.3 Structured Agent Outputs

The project moves away from brittle free-form JSON parsing and toward structured
Pydantic contracts for agent outputs.

The Deep Agent validator now prefers `CodeValidationResult` through structured
response support. The ADK content generator uses `AdkContentGenerationOutput` as
the target schema and keeps compatibility fallbacks where runtime support is
limited. This makes validation and generated learning content easier to test,
inspect, and safely consume.

### 4.4 Execution-Aware Code Correction

The system accepts caller-supplied execution evidence, including compile errors,
runtime errors, stdout, stderr, and test results. This allows the validator and
correction flow to reason from real VS Code or runtime signals instead of
pretending that a paid sandbox is always available.

This solves a practical learning problem: the system can respond to the exact
failure the learner encountered, then preserve that evidence for future memory.

### 4.5 Learner Memory Lifecycle

Coding attempts can be stored and consolidated into long-term memory notes.
Current memory types include error patterns, mastery signals, heuristics, and
background notes.

For example, if a learner repeatedly fails FastAPI async route exercises because
they forget `await`, the system can create an active error pattern and later a
teaching heuristic. Future content generation can then remind the learner about
async route-handler pitfalls before they fail again.

### 4.6 Hybrid Memory Retrieval

The memory retrieval system combines:

- pgvector semantic search over learner memory embeddings
- PostgreSQL full-text search through `search_text`
- scope-based retrieval using skillpath, content, and concept links
- Python reranking over a reduced candidate set

This solves the problem of retrieving only useful memory at the moment of
generation or correction, rather than fetching every active note and hoping the
agent handles it.

### 4.7 Roadmap-Aware and Memory-Aware Content Generation

Generated learning content can now receive a `LearningMemoryContext`. This means
articles, coding problems, explanations, and practice prompts can be shaped by
the learner's actual history.

The content-generation graph also receives the saved roadmap context: goal,
profile, milestones, skillpaths, selected practice modes, and content-planning
guidance. This lets generated material fit both the local learner memory and the
larger roadmap stage.

The intended behavior is not generic personalization like "beginner" or
"advanced". The target is specific personalization: "this learner often forgets
this concept, recently made this mistake, is currently on this skillpath, and
needs this kind of hint."

### 4.8 LangGraph Observability

The content-generation graph exposes retrieved memory in state through:

- `learning_memory_contexts_by_skillpath`
- `learning_memory_retrieval_diagnostics_by_skillpath`

The diagnostics distinguish whether retrieval was skipped, retrieved memory,
retrieved an empty context, or failed. This is important because an empty memory
state can mean many different things. The system should be debuggable, especially
when learning behavior depends on memory.

### 4.9 Graph-Based Project Research

Graphify is used as a research map over the project itself. The latest graph
contains code, plans, OpenSpec changes, tests, and research notes. It can help
answer questions such as:

- Which modules connect correction, validation, and memory?
- Which tests prove memory reaches content generation?
- What concepts bridge database retrieval and LangGraph state?
- Which inferred relationships need verification?
- Which parts of the system are weakly documented or isolated?

This makes the project easier to study as it grows.

## 5. Current Implementation Status

The current project has implemented the main memory-aware learning path.

Completed work includes:

- Learning director agent with MCP tools and local planner/content tools
- Roadmap generation from saved goal and learning profile
- Roadmap persistence, fetch, milestone update, and skillpath update services
- Roadmap review workflow through the roadmap-generation skill
- Content generation after saved roadmap review
- Generated learning-content persistence into saved skillpaths
- Structured code-validation output through `CodeValidationResult`
- External execution evidence fields for validation and correction
- Code-correction request mapping from validation results
- Learner memory storage for attempts, notes, and mastery state
- pgvector dependency and pgvector-ready PostgreSQL setup
- Full-text searchable `search_text` for memory notes
- Hybrid memory candidate retrieval in `learning_memory_retriever.py`
- Memory consolidation from repeated coding attempts
- Memory retrieval into `LearningMemoryContext`
- Memory injection into ADK content-generation requests
- LangGraph state visibility for retrieved memory contexts
- Retrieval diagnostics for skipped, empty, retrieved, and failed cases
- Non-live tests for memory retrieval, consolidation, correction, and content
  generation
- Planner, roadmap service, MCP tool, and learning director smoke coverage
- Gated live tests for real ADK and DB-backed memory integration

The main implementation record is archived at:

`openspec/changes/archive/2026-05-05-support-structured-output-pgvector-memory/`

Follow-up work is documented in:

- `openspec/changes/expose-learning-memory-context-in-langgraph-state/`
- `openspec/changes/add-learning-memory-retrieval-diagnostics/`
- `openspec/changes/add-live-graph-memory-smoke-and-trace-guards/`
- `openspec/changes/verify-memory-retrieval-agent-integration/`

## 6. Ongoing Work

The project is currently moving from "memory is connected" to "memory improves
learning quality" and from "roadmaps are generated" to "roadmaps adapt over
time."

The most important ongoing work is retrieval quality. The system needs stronger
evaluation data showing that the correct memory appears first for realistic
learner situations. Current tests prove the mechanics. Future tests should prove
ranking quality across many examples.

Another ongoing direction is hint customization. The goal is for hints to be
generated from what the learner typically forgets, what they are likely to
forget soon, and what they may be missing but have not explicitly asked about.
Hints should guide the learner rather than simply reveal the answer.

The system also needs stronger memory lifecycle rules. A memory note should not
stay equally important forever. Some memories should decay, some should be
resolved, some should become stronger after repeated evidence, and some should
be transformed into teaching heuristics.

Roadmap adaptation is also ongoing. The planner can generate and review a saved
roadmap, but the next step is to make learner memory actively reshape later
roadmap revisions. For example, repeated evidence of weak prerequisites should
cause the director to insert review skillpaths, change practice mode, adjust
estimated hours, or slow down before harder milestones.

Learning director policy is another active area. The director needs clearer
rules for when to generate a new roadmap, when to revise an existing one, when
to generate content, when to ask the learner a question, and when to use memory
or correction tools.

Live trace validation is also ongoing. The project now separates fake
deterministic tests from live ADK runs, but live tests still need regular manual
execution with credentials and a pgvector-enabled database.

## 7. Future Plan

The future plan is to develop Anti-pilot into a fully personalized learning path
system.

### 7.1 Personalized Learning Path Generation

Roadmaps should adapt to learner memory. If a learner repeatedly fails a concept,
the next skillpath should include review, contrast examples, and smaller
practice steps. If a learner shows mastery, the system should move faster or
increase difficulty.

The learning director should become responsible for this adaptation loop:
observe learner evidence, retrieve memory, inspect the saved roadmap, revise
only the necessary milestones or skillpaths, then generate or regenerate the
right learning content.

### 7.2 Predictive Forgetting Support

The system should estimate what the learner might forget soon. This can be based
on time since last practice, repeated mistakes, weak concepts, low confidence,
and missing prerequisite chains. The output should be timely review and
customized hints.

### 7.3 Fully Customized Hints

Hints should be generated from learner-specific memory. For example:

- If the learner usually forgets async behavior, hint toward event-loop and
  `await` reasoning.
- If the learner confuses data models and database models, show a comparison.
- If the learner has a repeated runtime error pattern, point to the likely cause
  before giving the solution.
- If the learner is missing a prerequisite, briefly teach that prerequisite
  inside the hint.

### 7.4 Retrieval Benchmarking

The project should build a small benchmark of learner histories and expected
retrieval results. This would make memory quality measurable instead of only
observable.

### 7.5 Reranking and Teaching Policy

A future reranker can operate over the current hybrid candidate set. Beyond
ranking, the system also needs a teaching policy: when to remind, when to ask a
question, when to give a partial hint, when to review, and when to advance.

### 7.6 Broader Agent Integration

The same `LearningMemoryContext` should eventually guide roadmap planning,
resource recommendation, project suggestions, review scheduling, and coding
feedback. The memory system should become the shared context layer for all
learning agents.

The learning director should be the coordinator across these agents. It should
decide which specialized capability to call, preserve user identity and saved
state, and keep the learner's roadmap coherent across many sessions.

### 7.7 Research Graph as Project Memory

Graphify should continue to act as a queryable research notebook. Each major
implementation phase should add records, OpenSpec artifacts, and verification
notes so future development can ask the graph what changed, why it changed, and
what remains uncertain.

## 8. Research Outlook

Anti-pilot is based on a simple claim: if coding agents are powerful enough to
teach anything, then learning software should stop being static. The next
generation of learning systems should remember the learner, adapt the path, and
guide practice based on evidence.

The project already contains the beginning of that system: structured agent
outputs, execution-aware correction, learner memory, hybrid retrieval,
memory-aware content generation, and observable graph state. The next research
challenge is to make that memory genuinely improve learning outcomes.

The desired endpoint is a learning agent that does not only answer, "What is the
solution?" It should understand, "What does this learner need next, and what are
they likely to forget if we do not guide them now?"
