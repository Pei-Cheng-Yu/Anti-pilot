MILESTONE_PROMPT = """
You are an expert learning roadmap planner.

Create a milestone-level learning plan for this learner.

Goal:
- Title: {goal_title}
- Description: {goal_description}
- Target outcome: {target_outcome}
- Deadline: {deadline}
- Success criteria: {criteria}
- Constraints: {constraints}

Learner profile:
- Baseline level: {baseline_level}
- Prior knowledges: {prior_knowledges}
- Weak areas: {weak_areas}
- Pace preference: {pace_preference}

Shared milestone policy:
{shared_milestone_policy}

Instructions:
- Follow the shared milestone policy when deciding milestone scope, sequencing, learner fit, and prerequisite reinforcement.
- Generate 3 to 7 milestones, ordered from foundational to advanced.
- The milestones should collectively cover the full learning journey required to achieve the target outcome.
- Avoid redundant or overlapping milestones.
- Dependencies must only reference earlier milestone IDs.
- estimated_hours should mean the approximate total learning time needed to complete that milestone.

Return JSON with this exact structure:
{{
  "milestones": [
    {{
      "milestone_id": "M1",
      "title": "...",
      "description": "...",
      "objective": "...",
      "estimated_hours": 0,
      "dependencies": []
    }}
  ]
}}
"""
QUICK_REVIEW_PROMPT = """
You are an expert learning roadmap reviewer.

Your task is to quickly review a milestone-level learning roadmap before skill path generation.

You will be given:
- the learner's goal
- the learner profile
- the generated milestones

Shared milestone policy:
{shared_milestone_policy}

Your review should focus only on major structural issues that would make downstream skill path generation unreliable, misleading, or wasteful.



Review criteria:

1. Goal alignment
- Do the milestones clearly support the target outcome?
- Are important success criteria covered?
- Is any essential milestone missing?

2. Learner fit
- Are the milestones appropriate for the learner's baseline level?
- Do they account for prior knowledge and weak areas?
- Is the pace realistic given the learner profile and constraints?

3. Sequencing
- Are milestones ordered from foundational to more advanced or applied stages?
- Is there any obvious sequencing problem?

4. Milestone scope
- Is any milestone far too broad, overloaded, or incoherent?
- Is any milestone too small or too trivial to be a meaningful milestone?

5. Dependency validity
- Are there any self-dependencies?
- Are there any invalid or nonsensical milestone dependencies?
- Are milestone dependencies obviously missing where they are clearly required?

6. Time realism
- Are milestone estimated hours obviously unrealistic?
- Does the roadmap look severely misaligned with the deadline or constraints?

Important instructions:
- Only report findings that are major enough to justify revising milestones before generating skill paths.
- Ignore small wording issues, minor naming problems, or small hour adjustments.
- If the roadmap is good enough to proceed, return no findings.
- A finding should be marked as "major" only if it should block or strongly suggest revising milestones first.

Return structured output as:
{{
  "proceed": true or false,
  "summary": "brief overall judgment",
  "findings": [
    {{
      "level": "major",
      "target_type": "roadmap" or "milestone",
      "target_id": "...",
      "issue_type": "...",
      "reason": "...",
      "suggested_action": "..."
    }}
  ]
}}
"""


REVISE_MILESTONE_PROMPT = """
You are an expert learning roadmap planner revising a milestone-level roadmap.

Your task is to revise the existing milestones based on review findings before skill path generation.

You will be given:
- the learner's goal
- the learner profile
- the current milestones
- milestone review findings

Shared milestone policy core:
{shared_milestone_policy_core}

Revision objective:
- Fix the problems identified in the review findings.
- Preserve the roadmap's valid structure and intent wherever possible.
- Make the smallest reasonable changes needed to resolve the major issues.
- Do not rewrite the roadmap unnecessarily if only part of it needs revision.

Goal:
- Title: {goal_title}
- Description: {goal_description}
- Target outcome: {target_outcome}
- Deadline: {deadline}
- Success criteria: {criteria}
- Constraints: {constraints}

Learner profile:
- Baseline level: {baseline_level}
- Prior knowledges: {prior_knowledges}
- Weak areas: {weak_areas}
- Pace preference: {pace_preference}

Current milestones:
{milestones}

Review findings to address:
{review_findings}

Instructions:
- Follow the shared milestone policy when revising milestone scope, sequencing, learner fit, weak-area onboarding, and prerequisite reinforcement.
- Revise only as much as needed to address the review findings.
- Do not introduce unrelated changes unless they are necessary to maintain roadmap coherence after a required revision.
- Keep milestones ordered from foundational to advanced.
- Keep the roadmap coherent and realistic for the learner's deadline and constraints.
- Preserve milestones that are already valid unless a review finding implies they must change.
- You may add, remove, split, merge, reorder, or rewrite milestones if needed, but only when justified by the findings.
- If one milestone changes substantially, update downstream milestones or dependencies only as needed to maintain coherence.
- Avoid redundant or overlapping milestones.
- Dependencies must only reference earlier milestone IDs.
- Reassign milestone IDs cleanly in sequence as M1, M2, M3, ... in final output.
- estimated_hours should mean the approximate total learning time needed to complete that milestone.

Output requirements:
- Return the revised full milestone list, not a patch, explanation, or diff.
- The revised roadmap should be internally coherent and ready for skill path generation.

Return JSON with this exact structure:
{{
  "milestones": [
    {{
      "milestone_id": "M1",
      "title": "...",
      "description": "...",
      "objective": "...",
      "estimated_hours": 0,
      "dependencies": []
    }}
  ]
}}
"""

SKILLPATH_PROMPT = """
    You are an expert learning roadmap planner.

    Your task is to generate skill paths for exactly one milestone in a learning roadmap.

    A skill path is:
    - a coherent learning unit under one milestone
    - larger than a single task or exercise
    - smaller and more specific than the milestone itself
    - a unit that can later have detailed learning content, exercises, and resources generated under it

    Goal context:
    - Title: {goal_title}
    - Target outcome: {goal_outcome}
    - Constraints: {goal_constraints}

    Learner profile:
    - Baseline level: {learning_baseline_level}
    - Prior knowledges: {learning_prior_knowledges}
    - Weak areas: {learning_weak_areas}
    - Pace preference: {learning_pace_preference}

    Milestone:
    - Title: {milestone_title}
    - Description: {milestone_description}
    - Objective: {milestone_objective}
    - Estimated hours: {milestone_estimated_hours}

    Instructions:
    1. Generate 3 to 5 skill paths for this milestone.
    2. Every skill path must stay strictly within the scope of this milestone.
    3. Do not generate task-level items such as "read one article", "install package", or "write one endpoint".
    4. Do not repeat the milestone title as a skill path title unless it is truly necessary.
    5. Each skill path title must be unique within this batch.
    6. Order skill paths from more foundational to more advanced or applied.
    7. Adapt the skill paths to the learner's baseline level, prior knowledge, weak areas, and pace preference.
    8. The combined estimated hours of all skill paths should be reasonably close to the milestone estimated hours.
    9. Skill paths should be concrete and focused, not vague or overly broad.

    Dependency rules:
    1. Use depends_on_titles only when a skill path truly requires another skill path in this same batch.
    2. Every dependency title must exactly match the title of another generated skill path in this same batch.
    3. Never make a skill path depend on itself.
    4. Never reference the milestone title, goal title, or any title not generated in this batch.
    5. If no prerequisite is needed, return an empty list.
    6. Prefer minimal dependencies. Do not add dependencies unless they are clearly necessary.

    Quality checks before finalizing your answer:
    - No self-dependencies
    - No dependency on titles outside this batch
    - No duplicate titles
    - No task-level items
    - No skill path that is unrelated to the milestone
    - No skill path that is almost identical to the milestone title unless justified

    Return structured output with:
    - title
    - description
    - estimated_hours
    - learning_objectives
    - depends_on_titles
    """
