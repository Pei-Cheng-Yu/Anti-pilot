from collections import defaultdict
from typing import Optional

from app.schema.entities import MilestoneItem, SkillPathItem
from pydantic import BaseModel


class SkillPathReviewBundle(BaseModel):
    skillpaths: list[SkillPathItem]
    milestone: Optional[MilestoneItem] = None


def wrap_skillpaths_with_milestones(
    skillpaths: list[SkillPathItem],
    milestones: list[MilestoneItem],
) -> list[SkillPathReviewBundle]:
    milestone_map = {m.milestone_id: m for m in milestones}
    grouped_skillpaths: dict[str, list[SkillPathItem]] = defaultdict(list)

    for sp in skillpaths:
        grouped_skillpaths[sp.milestone_id].append(sp)

    bundles = []
    for milestone_id, grouped_sps in grouped_skillpaths.items():
        bundles.append(
            SkillPathReviewBundle(
                milestone=milestone_map.get(milestone_id),
                skillpaths=grouped_sps,
            )
        )

    return bundles


def format_skillpaths(skillpaths: list[dict]) -> str:
    lines = []
    for sp in skillpaths:
        lines.append(
            f"- SkillPath ID: {sp.get('skillpath_id', '')}\n"
            f"  Title: {sp.get('title', '')}\n"
            f"  Description: {sp.get('description', '')}\n"
            f"  Estimated hours: {sp.get('estimated_hours', '')}\n"
            f"  Prerequisite skillpath IDs: {sp.get('prerequisite_skillpath_ids', [])}\n"
            f"  Learning objectives: {sp.get('learning_objectives', [])}"
        )
    return "\n".join(lines)
