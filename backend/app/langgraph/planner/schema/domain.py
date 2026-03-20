from pydantic import BaseModel, Field


class SkillPath(BaseModel):
    skillpath_id: str
    milestone_id: str
    title: str
    description: str
    estimated_hours: float
    prerequisite_skillpath_ids: list[str]
    learning_objectives: list[str] = Field(default_factory=list)
    affected_downstream_ids: list[str] = Field(default_factory=list)


class Milestone(BaseModel):
    roadmap_id: str
    milestone_id: str
    title: str
    description: str
    estimated_hours: float
    order_index: int
    skillpaths: list[SkillPath]


class Roadmap(BaseModel):
    version: int
    summary: str
    milestone: list[Milestone]
    assumptions: list[str] = Field(default_factory=list)
    target_outcome: str
