from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    brief: str = Field(min_length=20, max_length=6000)
    research_questions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    report_type: str = Field(default="strategic_report", max_length=64)
    output_language: str = Field(default="English", max_length=64)
    max_findings: int = Field(default=8, ge=3, le=30)
    search_depth: int = Field(default=2, ge=1, le=4)
    html_requested: bool = False
    run_interval_minutes: int | None = Field(default=60, ge=15)

    @field_validator("research_questions", "entities", "focus_areas")
    @classmethod
    def strip_list_items(cls, values: list[str]) -> list[str]:
        return [item.strip() for item in values if item.strip()]


class PipelineStageRead(BaseModel):
    id: int
    task_id: int
    stage_key: str
    stage_title: str
    phase: str
    stage_order: int
    stage_kind: str
    attempt: int
    status: str
    summary: str | None
    payload_json: dict[str, object]
    score: float | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResearchTaskRead(ResearchTaskCreate):
    id: int
    status: str
    current_stage: str | None
    search_queries: list[str]
    pipeline_state: dict[str, object]
    report_paths: dict[str, str]
    final_report_markdown: str | None
    final_report_html: str | None
    error_message: str | None
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    stages: list[PipelineStageRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TaskApprovalRequest(BaseModel):
    start_html_design: bool = False


class HealthRead(BaseModel):
    status: str
    database: str
    mode: str
