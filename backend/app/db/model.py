from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)


class UserModel(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    goals: Mapped[list["GoalModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    learning_profile: Mapped["LearningProfileModel"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    roadmaps: Mapped[list["RoadmapModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    coding_problem_attempts: Mapped[list["CodingProblemAttemptModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    skill_mastery_states: Mapped[list["SkillMasteryStateModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    learner_memory_notes: Mapped[list["LearnerMemoryNoteModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    discovery_conversations: Mapped[list["DiscoveryConversationModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class GoalModel(Base):
    __tablename__ = "goals"
    __table_args__ = (UniqueConstraint("goal_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goal_id: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.user_id"))
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    target_outcome: Mapped[str] = mapped_column(Text)
    deadline: Mapped[date] = mapped_column(Date)
    criteria: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    constraints: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    user: Mapped["UserModel"] = relationship(back_populates="goals")
    roadmaps: Mapped[list["RoadmapModel"]] = relationship(back_populates="goal")


class LearningProfileModel(Base):
    __tablename__ = "learning_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id"), unique=True
    )
    baseline_level: Mapped[str] = mapped_column(
        String
    )  # beginner / intermediate / advanced
    prior_knowledges: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    weak_areas: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    pace_preference: Mapped[str] = mapped_column(String)  # slow / balanced / intensive
    confidence_level: Mapped[str] = mapped_column(String)  # low / medium / high
    needs_recap: Mapped[bool]
    prefers_examples_first: Mapped[bool]
    overload_risk: Mapped[str] = mapped_column(String)  # low / medium / high

    user: Mapped["UserModel"] = relationship(back_populates="learning_profile")


class RoadmapModel(Base):
    __tablename__ = "roadmaps"
    __table_args__ = (UniqueConstraint("goal_id"),)

    roadmap_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.user_id"))
    goal_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("goals.goal_id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String, default="")
    version: Mapped[int]
    summary: Mapped[str] = mapped_column(Text)
    target_outcome: Mapped[str] = mapped_column(Text)
    assumptions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    user: Mapped["UserModel"] = relationship(back_populates="roadmaps")
    goal: Mapped["GoalModel"] = relationship(back_populates="roadmaps")
    milestones: Mapped[list["MilestoneModel"]] = relationship(
        back_populates="roadmap", cascade="all, delete-orphan"
    )


class MilestoneModel(Base):
    __tablename__ = "milestones"

    milestone_id: Mapped[str] = mapped_column(String, primary_key=True)
    roadmap_id: Mapped[str] = mapped_column(String, ForeignKey("roadmaps.roadmap_id"))
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    objective: Mapped[str] = mapped_column(Text)
    estimated_hours: Mapped[float]
    order_index: Mapped[int]
    dependency_titles: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    prerequisite_milestone_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list
    )
    status: Mapped[str] = mapped_column(String, default="ready")
    need_modification: Mapped[bool] = mapped_column(default=False)
    revision_reason: Mapped[str | None] = mapped_column(Text)

    roadmap: Mapped["RoadmapModel"] = relationship(back_populates="milestones")
    skillpaths: Mapped[list["SkillPathModel"]] = relationship(
        back_populates="milestone", cascade="all, delete-orphan"
    )


class SkillPathModel(Base):
    __tablename__ = "skillpaths"

    skillpath_id: Mapped[str] = mapped_column(String, primary_key=True)
    milestone_id: Mapped[str] = mapped_column(
        String, ForeignKey("milestones.milestone_id")
    )
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    estimated_hours: Mapped[float]
    prerequisite_skillpath_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list
    )
    learning_objectives: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    status: Mapped[str] = mapped_column(String, default="ready")
    need_generation: Mapped[bool] = mapped_column(default=False)
    need_modification: Mapped[bool] = mapped_column(default=False)
    revision_reason: Mapped[str | None] = mapped_column(Text)
    affected_downstream_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list
    )
    practice_mode: Mapped[str | None] = mapped_column(String, nullable=True)

    milestone: Mapped["MilestoneModel"] = relationship(back_populates="skillpaths")
    learning_contents: Mapped[list["LearningContentModel"]] = relationship(
        back_populates="skillpath", cascade="all, delete-orphan"
    )


class LearningContentModel(Base):
    __tablename__ = "learning_contents"

    content_id: Mapped[str] = mapped_column(String, primary_key=True)
    skillpath_id: Mapped[str] = mapped_column(
        String, ForeignKey("skillpaths.skillpath_id")
    )
    content_type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)

    skillpath: Mapped["SkillPathModel"] = relationship(
        back_populates="learning_contents"
    )


class ReviewConceptModel(Base):
    __tablename__ = "review_concepts"

    concept_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True, default="default-user")
    source_type: Mapped[str] = mapped_column(String)
    source_ref_id: Mapped[str] = mapped_column(String)
    concept_metadata: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[int] = mapped_column(Integer)
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stability: Mapped[float] = mapped_column(Float, default=0.0)
    difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    elapsed_days: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_days: Mapped[int] = mapped_column(Integer, default=0)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CodingProblemAttemptModel(Base):
    __tablename__ = "coding_problem_attempts"

    attempt_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.user_id"))
    skillpath_id: Mapped[str] = mapped_column(
        String, ForeignKey("skillpaths.skillpath_id")
    )
    content_id: Mapped[str] = mapped_column(String)
    submitted_code: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String)
    correctness: Mapped[str] = mapped_column(String)
    feedback_summary: Mapped[str] = mapped_column(Text)
    detected_concepts: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    detected_mistakes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    compile_error: Mapped[str | None] = mapped_column(Text)
    runtime_error: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)
    test_results: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["UserModel"] = relationship(back_populates="coding_problem_attempts")


class SkillMasteryStateModel(Base):
    __tablename__ = "skill_mastery_states"
    __table_args__ = (UniqueConstraint("user_id", "skillpath_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.user_id"))
    skillpath_id: Mapped[str] = mapped_column(
        String, ForeignKey("skillpaths.skillpath_id")
    )
    status: Mapped[str] = mapped_column(String)
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0)
    successful_attempts: Mapped[int] = mapped_column(Integer, default=0)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    strong_concepts: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    weak_concepts: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["UserModel"] = relationship(back_populates="skill_mastery_states")


class LearnerMemoryNoteModel(Base):
    __tablename__ = "learner_memory_notes"

    memory_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.user_id"))
    memory_type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    linked_concepts: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    linked_skillpath_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    linked_content_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    evidence_attempt_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(3072))
    search_text: Mapped[str] = mapped_column(Text, default="")
    salience_score: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped["UserModel"] = relationship(back_populates="learner_memory_notes")


class DiscoveryConversationModel(Base):
    __tablename__ = "discovery_conversations"

    conversation_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.user_id"))
    goal_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("goals.goal_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["UserModel"] = relationship(back_populates="discovery_conversations")
