from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


def json_type():
    return JSON().with_variant(JSONB, "postgresql")


class TaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    awaiting_review = "awaiting_review"
    completed = "completed"
    failed = "failed"


class ResearchTask(Base):
    __tablename__ = "research_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    brief: Mapped[str] = mapped_column(Text)
    research_questions: Mapped[list[str]] = mapped_column(MutableList.as_mutable(json_type()), default=list)
    entities: Mapped[list[str]] = mapped_column(MutableList.as_mutable(json_type()), default=list)
    focus_areas: Mapped[list[str]] = mapped_column(MutableList.as_mutable(json_type()), default=list)
    report_type: Mapped[str] = mapped_column(String(64), default="strategic_report")
    output_language: Mapped[str] = mapped_column(String(64), default="English")
    max_findings: Mapped[int] = mapped_column(Integer, default=8)
    search_depth: Mapped[int] = mapped_column(Integer, default=2)
    html_requested: Mapped[bool] = mapped_column(default=False)
    run_interval_minutes: Mapped[int | None] = mapped_column(Integer, default=60, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.queued.value, index=True)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    search_queries: Mapped[list[str]] = mapped_column(MutableList.as_mutable(json_type()), default=list)
    pipeline_state: Mapped[dict[str, object]] = mapped_column(MutableDict.as_mutable(json_type()), default=dict)
    report_paths: Mapped[dict[str, str]] = mapped_column(MutableDict.as_mutable(json_type()), default=dict)
    final_report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_report_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    stages: Mapped[list["PipelineStage"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    logs: Mapped[list["RunLog"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    report_artifacts: Mapped[list["ReportArtifact"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class StageStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    awaiting_approval = "awaiting_approval"
    skipped = "skipped"


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (UniqueConstraint("task_id", "stage_key", "attempt", name="uq_pipeline_stage_attempt"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True)
    stage_key: Mapped[str] = mapped_column(String(64), index=True)
    stage_title: Mapped[str] = mapped_column(String(255))
    phase: Mapped[str] = mapped_column(String(64))
    stage_order: Mapped[int] = mapped_column(Integer, index=True)
    stage_kind: Mapped[str] = mapped_column(String(32), default="work")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default=StageStatus.pending.value, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(MutableDict.as_mutable(json_type()), default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[ResearchTask] = relationship(back_populates="stages")


class RunLog(Base):
    __tablename__ = "run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String(32), default="info")
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, object]] = mapped_column(MutableDict.as_mutable(json_type()), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[ResearchTask] = relationship(back_populates="logs")


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(32), default="docx", index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    task: Mapped[ResearchTask] = relationship(back_populates="report_artifacts")
