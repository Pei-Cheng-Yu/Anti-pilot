from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, MetaData, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
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

    goal: Mapped["GoalModel"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    learning_profile: Mapped["LearningProfileModel"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    roadmaps: Mapped[list["RoadmapModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class GoalModel(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id"), unique=True
    )
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    target_outcome: Mapped[str] = mapped_column(Text)
    deadline: Mapped[date] = mapped_column(Date)
    criteria: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    constraints: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    user: Mapped["UserModel"] = relationship(back_populates="goal")


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

    roadmap_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.user_id"))
    version: Mapped[int]
    summary: Mapped[str] = mapped_column(Text)
    target_outcome: Mapped[str] = mapped_column(Text)
    assumptions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    user: Mapped["UserModel"] = relationship(back_populates="roadmaps")
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

    milestone: Mapped["MilestoneModel"] = relationship(back_populates="skillpaths")
