from uuid import uuid4

from app.schema.entities import (
    ArticleLearningContent,
    CodingProblemLearningContent,
    ContentSourceNote,
    MultipleChoiceLearningContent,
    MultipleChoiceOption,
    SkillPathItem,
    SourceLink,
)


def apply_content_drafts(
    skillpaths: list[SkillPathItem], content_drafts: list[dict]
) -> list[SkillPathItem]:
    skillpath_map = {
        item.skillpath_id: item.model_copy(deep=True) for item in skillpaths
    }

    for draft in content_drafts:
        skillpath_id = draft["skillpath_id"]
        skillpath = skillpath_map.get(skillpath_id)
        if not skillpath:
            continue

        article = draft["article"]
        contents = [
            ArticleLearningContent(
                content_id=str(uuid4()),
                skillpath_id=skillpath_id,
                title=article["title"],
                description=article["description"],
                skill_intro=article["skill_intro"],
                reading_content=article["reading_content"],
                references=[
                    SourceLink(**reference)
                    for reference in article.get("references", [])
                ],
                source_notes=[
                    ContentSourceNote(
                        source=SourceLink(**note["source"]),
                        note=note["note"],
                    )
                    for note in article.get("source_notes", [])
                ],
            )
        ]

        coding_problem = draft.get("coding_problem")
        if coding_problem:
            contents.append(
                CodingProblemLearningContent(
                    content_id=str(uuid4()),
                    skillpath_id=skillpath_id,
                    title=coding_problem["title"],
                    description=coding_problem["description"],
                    prompt=coding_problem["prompt"],
                    difficulty=coding_problem["difficulty"],
                    starter_code=coding_problem.get("starter_code"),
                    expected_output=coding_problem.get("expected_output"),
                    hints=coding_problem.get("hints", []),
                )
            )

        multiple_choice = draft.get("multiple_choice")
        if multiple_choice:
            contents.append(
                MultipleChoiceLearningContent(
                    content_id=str(uuid4()),
                    skillpath_id=skillpath_id,
                    title=multiple_choice["title"],
                    description=multiple_choice["description"],
                    question=multiple_choice["question"],
                    options=[
                        MultipleChoiceOption(**option)
                        for option in multiple_choice.get("options", [])
                    ],
                    correct_option_id=multiple_choice["correct_option_id"],
                    explanation=multiple_choice["explanation"],
                )
            )

        skillpath.learning_contents = contents
        skillpath.need_generation = False
        skillpath.status = "generated"

    ordered = []
    for skillpath in skillpaths:
        ordered.append(skillpath_map.get(skillpath.skillpath_id, skillpath))
    return ordered
