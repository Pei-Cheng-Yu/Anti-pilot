SHARED_SKILLPATH_POLICY = """
Skill path planning policy:

1. A skill path should represent one coherent learning unit.
- A skill path should be more specific than a milestone, but larger than a single micro-task.
- It should usually focus on one closely related concept cluster, practice area, or implementation step.
- A skill path should feel like one meaningful chunk of progress that can later be broken into tasks.

2. A skill path should clearly support its parent milestone.
- Every skill path should directly contribute to the milestone’s objective.
- Do not include content that is only loosely related or that belongs to a later milestone.
- If a skill path introduces material beyond the milestone’s intended scope, that is a review issue.

3. Skill path granularity should adapt to pace preference.
- slow:
  - Use smaller, more guided skill paths.
  - Prefer narrower scope, fewer new ideas at once, and lower conceptual jump.
  - Separate foundation, guided practice, and applied usage when the learner is still building confidence.
- balanced:
  - Use moderate-sized skill paths.
  - A skill path may combine closely related concepts and a small amount of practice if the learning jump is still reasonable.
- intensive:
  - Allow broader skill paths, but they must remain coherent.
  - A skill path may combine multiple closely related ideas if the learner can realistically absorb and apply them together.

4. Skill path granularity should adapt to learner readiness.
- beginner:
  - Prefer smaller skill paths with clearer conceptual boundaries.
  - Avoid combining foundations, applied implementation, and debugging/integration in the same skill path unless the topic is very simple.
  - Reduce jump size between adjacent skill paths.
- intermediate:
  - A skill path can combine concept learning with initial implementation when the topics are closely related.
  - Moderate abstraction and moderate implementation breadth are acceptable.
- advanced:
  - A skill path may be broader and more integration-oriented, as long as it still represents one coherent unit of learning.

5. Weak areas should be introduced in a learner-friendly way within the approved milestone scope.
- If the milestone includes work in a learner weak area, the first related skill path inside this milestone should provide an approachable entry point when possible.
- Do not require adding entirely new prerequisite domains if those belong to earlier milestone planning rather than this milestone decomposition.

6. A skill path should not hide too many new ideas.
- A skill path is too broad if it introduces too many unfamiliar concepts, tools, abstractions, and implementation demands at once.
- A skill path is too compressed if the learner would likely need to mentally split it into multiple stages to complete it successfully.
- As a rule of thumb, a skill path should usually cover one main learning theme and at most a small number of tightly related subtopics.

7. A skill path should not be too fragmented.
- Do not split a skill path so small that it becomes a trivial checklist item.
- A skill path should not be just one tiny operation, one isolated command, or one overly narrow micro-concept unless the learner truly needs extremely fine-grained scaffolding.
- Over-fragmentation reduces roadmap coherence and makes downstream planning noisy.

8. Foundations should come before dependency-heavy application within the skill path set.
- If one skill path depends on concepts introduced by another skill path in this same milestone, the foundation-oriented skill path should come first.
- Do not treat missing broader background from outside this milestone as a skillpath-level issue unless the current set cannot realistically support the milestone objective.

9. A skill path should be practical for downstream task generation.
- A good skill path should be concrete enough that later nodes can generate tasks, exercises, mini-projects, or resources from it.
- If a skill path is too abstract, too vague, or too broad to translate into actionable next steps, it should be flagged.

10. Use prior knowledge to avoid unnecessary splitting.
- If the learner already knows the basics of an area, do not over-split that area into too many elementary skill paths.
- Preserve efficiency while still keeping learning progression coherent.

Examples of good granularity:
- Beginner + slow pace:
  - Separate "HTTP request/response basics" from "REST API design basics" and from "Build CRUD endpoints with FastAPI".
- Beginner + weak database background:
  - Separate "Relational modeling basics" from "SQL querying basics" and from "Using SQLAlchemy models in FastAPI".
- Intermediate + balanced pace:
  - It may be reasonable to combine "FastAPI routing and request handling" into one skill path.
- Advanced + intensive pace:
  - It may be reasonable to combine "API validation, error handling, and dependency injection" into one skill path if they are tightly related and the learner is ready.

Examples of poor granularity:
- Too broad:
  - "Learn backend development with FastAPI, database design, authentication, and deployment"
- Too fragmented:
  - "Install FastAPI"
  - "Write one GET endpoint"
  - "Read about request body"
  when these are split without a real pedagogical reason.
"""
SHARED_SKILLPATH_POLICY_CORE = """
Skill path planning policy:
- A skill path should represent one coherent learning unit, smaller than a milestone but larger than a micro-task.
- Match skill path scope and granularity to the learner’s baseline, prior knowledge, weak areas, pace preference, and constraints.
- For weak areas, begin with learner-friendly foundation skill paths before implementation-heavy or dependency-heavy work.
- Make prerequisite concepts explicit before integration-heavy, optimization-heavy, or production-heavy skill paths.
- Avoid overly broad skill paths that hide too many new concepts, tools, abstractions, or implementation demands at once.
- Use prior knowledge to avoid unnecessary splitting or repetition.
- Avoid over-fragmented skill paths that become trivial checklist items or isolated micro-steps.
- Keep skill paths concrete, coherent, and actionable for downstream task, exercise, project, resource, or review generation.

Examples of good granularity:
- Beginner + slow pace:
  - Separate "HTTP request/response basics" from "REST API design basics" and from "Build CRUD endpoints with FastAPI".
- Beginner + weak database background:
  - Separate "Relational modeling basics" from "SQL querying basics" and from "Using SQLAlchemy models in FastAPI".
- Intermediate + balanced pace:
  - It may be reasonable to combine "FastAPI routing and request handling" into one skill path.
- Advanced + intensive pace:
  - It may be reasonable to combine "API validation, error handling, and dependency injection" into one skill path if they are tightly related and the learner is ready.

Examples of poor granularity:
- Too broad:
  - "Learn backend development with FastAPI, database design, authentication, and deployment"
- Too fragmented:
  - "Install FastAPI"
  - "Write one GET endpoint"
  - "Read about request body"
  when these are split without a real pedagogical reason.
"""
