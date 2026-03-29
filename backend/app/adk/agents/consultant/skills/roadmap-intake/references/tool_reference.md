# Tools Reference

Use these tools to store state. All parameters are optional — pass only what is
currently known. Call incrementally as information becomes available.

## store_goal_spec
```python
store_goal_spec(
    title: str | None,
    description: str | None,
    target_outcome: str | None,
    deadline: str | None,        #using specific date e.g. "2024-09-01"
    criteria: list[str] | None,
    constraints: list[str] | None,
)
```

## store_learning_profile
```python
store_learning_profile(
    baseline_level: str | None,  # "beginner" | "intermediate" | "advanced"
    prior_knowledges: list[str] | None,
    weak_areas: list[str] | None,
    pace_preference: str | None, # "slow" | "balanced" | "intensive"
    confidence_level: str | None,# "low" | "medium" | "high"
    needs_recap: bool | None,
    prefers_examples_first: bool | None,
    overload_risk: str | None,   # "low" | "medium" | "high"
)
```
