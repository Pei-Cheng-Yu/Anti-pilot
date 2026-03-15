SHARED_MILESTONE_POLICY = """
Milestone planning policy:

1. Milestones should represent meaningful stages of learning.
- A milestone should capture a coherent learning phase, not a checklist of small tasks.
- Each milestone should have a clear purpose in moving the learner toward the target outcome.

2. Milestones should match the learner’s readiness.
- Adapt milestone difficulty, scope, and abstraction level to the learner’s baseline level and prior knowledge.
- Avoid combining too many new ideas in one milestone when the learner is still building foundations.
- For beginner learners, reduce conceptual jump size between milestones.

3. Weak areas should receive a learner-friendly entry point.
- When the learner is weak in an area that is important for later progress, include an approachable starting milestone or early stage for that area.
- The first milestone touching a weak area should introduce the core ideas, vocabulary, mental model, and basic practice before expecting complex application.
- Weak areas should be introduced in a way that builds confidence, not immediate performance pressure.

4. Foundations should come before dependency-heavy application.
- If later milestones rely on a missing or weak prerequisite, the roadmap should make that prerequisite explicit earlier.
- Foundational understanding should come before implementation-heavy, integration-heavy, or optimization-heavy work.

5. Milestone size should reflect pace preference.
- slow: use finer-grained milestones with smaller learning jumps
- balanced: use moderate milestone scope
- intensive: allow broader milestones, but keep them coherent and learnable

6. Use prior knowledge to avoid unnecessary repetition.
- Do not reteach material the learner already knows unless it is needed for integration, correction, or confidence rebuilding.
- If the learner is already strong in an area, move faster through it while preserving roadmap coherence.

7. Milestones should stay coherent in scope.
- Do not mix unrelated learning goals in the same milestone.
- A milestone may combine closely related concepts and practice, but it should still feel like one meaningful stage.
- A milestone may be too broad if it introduces foundations, first application, and advanced integration all at once for a learner who is not yet confident in that area.

8. Milestones should support realistic progression.
- The overall roadmap should be feasible under the stated deadline and constraints.
- Milestones should be ordered so that each stage prepares the learner for the next.

Examples of policy application:
- If the learner is weak in database design, begin with a milestone that builds comfort with data modeling, tables, relationships, and query thinking before ORM integration or persistence-heavy backend features.
- If the learner is weak in HTTP or web APIs, begin with a milestone that explains request/response flow, routes, methods, and API basics before CRUD design, authentication, or deployment.
- If the learner is weak in Git, begin with a milestone that builds confidence with everyday version control workflows before collaborative branching, release flow, or CI/CD-related practices.
- If the learner already has strong programming fundamentals, avoid spending a full milestone reteaching syntax unless the goal specifically requires it.
"""

SHARED_MILESTONE_POLICY_CORE = """
Milestone planning policy:
- A milestone should represent a meaningful learning stage, not a task list.
- Match milestone scope and difficulty to the learner’s baseline, prior knowledge, weak areas, pace preference, and constraints.
- For weak areas, provide a learner-friendly starting point before complex application.
- Make missing prerequisites explicit before dependency-heavy implementation.
- Avoid overly broad milestones, especially for beginners or learners lacking confidence in that area.
- Use prior knowledge to avoid unnecessary repetition.
- Keep milestones coherent, sequential, and realistic for the deadline.

Examples of policy application:
- If the learner is weak in database design, begin with a milestone that builds comfort with data modeling, tables, relationships, and query thinking before ORM integration or persistence-heavy backend features.
- If the learner is weak in HTTP or web APIs, begin with a milestone that explains request/response flow, routes, methods, and API basics before CRUD design, authentication, or deployment.
- If the learner is weak in Git, begin with a milestone that builds confidence with everyday version control workflows before collaborative branching, release flow, or CI/CD-related practices.
- If the learner already has strong programming fundamentals, avoid spending a full milestone reteaching syntax unless the goal specifically requires it.
"""
