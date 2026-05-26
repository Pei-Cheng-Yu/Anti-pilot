from collections import defaultdict
from uuid import uuid4

from app.langgraph.planner.schema.entities import SkillPathItem


def finalize_skillpaths(roadmap_id: str, skillpath_drafts: list[dict]) -> list[SkillPathItem]:
    title_to_id = {}
    items = []

    for draft in skillpath_drafts:
        sid = str(uuid4())
        title_to_id[(draft["milestone_id"], draft["title"])] = sid

        items.append(
            SkillPathItem(
                roadmap_id=roadmap_id,
                skillpath_id=sid,
                milestone_id=draft["milestone_id"],
                title=draft["title"],
                description=draft["description"],
                estimated_hours=draft["estimated_hours"],
                learning_objectives=draft["learning_objectives"],
                prerequisite_skillpath_ids=[],
                status="ready",
                need_generation=True,
                need_modification=False,
                revision_reason=None,
                affected_downstream_ids=[],
            )
        )

    item_map = {(item.milestone_id, item.title): item for item in items}

    # resolve prerequisites
    for draft in skillpath_drafts:
        item = item_map[(draft["milestone_id"], draft["title"])]
        for dep_title in draft["depends_on_titles"]:
            dep_id = title_to_id.get((draft["milestone_id"], dep_title))
            if dep_id:
                item.prerequisite_skillpath_ids.append(dep_id)

    # direct reverse edges
    reverse_graph = defaultdict(list)
    for item in items:
        for prereq_id in item.prerequisite_skillpath_ids:
            reverse_graph[prereq_id].append(item.skillpath_id)

    # transitive downstream
    def collect_descendants(start_id: str) -> list[str]:
        seen = set()
        stack = list(reverse_graph[start_id])
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(reverse_graph[cur])
        return list(seen)

    for item in items:
        item.affected_downstream_ids = collect_descendants(item.skillpath_id)

    return items
