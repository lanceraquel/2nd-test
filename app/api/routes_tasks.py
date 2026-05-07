from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_session
from app.models import PipelineStage, ReportArtifact, ResearchTask, TaskStatus
from app.reports.exporter import export_task_reports
from app.research.openai_pipeline import approve_task, rerun_task
from app.schemas import ResearchTaskCreate, ResearchTaskRead, TaskApprovalRequest

router = APIRouter(tags=["runs"])


@router.post("/runs", response_model=ResearchTaskRead, status_code=201)
@router.post("/tasks", response_model=ResearchTaskRead, status_code=201)
def create_task(payload: ResearchTaskCreate, session: Session = Depends(get_session)) -> ResearchTask:
    task = ResearchTask(**payload.model_dump())
    session.add(task)
    session.commit()
    return _get_task_or_404(session, task.id)


@router.get("/runs", response_model=list[ResearchTaskRead])
@router.get("/tasks", response_model=list[ResearchTaskRead])
def list_tasks(session: Session = Depends(get_session)) -> list[ResearchTask]:
    stmt = select(ResearchTask).options(selectinload(ResearchTask.stages)).order_by(ResearchTask.created_at.desc())
    return list(session.scalars(stmt).unique().all())


@router.get("/runs/{task_id}", response_model=ResearchTaskRead)
@router.get("/tasks/{task_id}", response_model=ResearchTaskRead)
def get_task(task_id: int, session: Session = Depends(get_session)) -> ResearchTask:
    return _get_task_or_404(session, task_id)


@router.post("/runs/{task_id}/run", response_model=ResearchTaskRead)
@router.post("/tasks/{task_id}/run", response_model=ResearchTaskRead)
def queue_task_run(task_id: int, session: Session = Depends(get_session)) -> ResearchTask:
    task = session.get(ResearchTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if task.status == TaskStatus.running.value:
        raise HTTPException(status_code=409, detail="Run is already running")
    rerun_task(session, task)
    return _get_task_or_404(session, task_id)


@router.post("/runs/{task_id}/approve", response_model=ResearchTaskRead)
def approve_run(
    task_id: int,
    payload: TaskApprovalRequest,
    session: Session = Depends(get_session),
) -> ResearchTask:
    task = session.get(ResearchTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if task.status != TaskStatus.awaiting_review.value:
        raise HTTPException(status_code=409, detail="Run is not awaiting human review")
    approve_task(session, task, start_html_design=payload.start_html_design)
    return _get_task_or_404(session, task_id)


@router.post("/runs/{task_id}/reports", response_model=dict[str, str])
@router.post("/tasks/{task_id}/reports", response_model=dict[str, str])
def generate_reports(task_id: int, session: Session = Depends(get_session)) -> dict[str, str]:
    task = session.get(ResearchTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Run not found")
    report_paths = export_task_reports(session, task)
    task.report_paths = report_paths
    session.commit()
    return report_paths


@router.get("/runs/{task_id}/stages")
def list_run_stages(task_id: int, session: Session = Depends(get_session)) -> list[dict[str, object]]:
    if session.get(ResearchTask, task_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    stages = list(
        session.scalars(
            select(PipelineStage).where(PipelineStage.task_id == task_id).order_by(PipelineStage.stage_order.asc(), PipelineStage.attempt.asc())
        ).all()
    )
    return [
        {
            "id": stage.id,
            "stage_key": stage.stage_key,
            "stage_title": stage.stage_title,
            "phase": stage.phase,
            "stage_order": stage.stage_order,
            "attempt": stage.attempt,
            "status": stage.status,
            "summary": stage.summary,
            "payload_json": stage.payload_json,
            "started_at": stage.started_at,
            "completed_at": stage.completed_at,
        }
        for stage in stages
    ]


@router.get("/runs/{task_id}/reports/latest.docx")
@router.get("/tasks/{task_id}/reports/latest.docx")
def download_latest_docx_report(task_id: int, session: Session = Depends(get_session)) -> Response:
    if session.get(ResearchTask, task_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    artifact = session.scalar(
        select(ReportArtifact)
        .where(ReportArtifact.task_id == task_id, ReportArtifact.format == "docx")
        .order_by(ReportArtifact.created_at.desc())
        .limit(1)
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="No DOCX report has been generated for this run yet")
    return Response(
        content=artifact.content,
        media_type=artifact.content_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )


def _get_task_or_404(session: Session, task_id: int) -> ResearchTask:
    stmt = select(ResearchTask).where(ResearchTask.id == task_id).options(selectinload(ResearchTask.stages))
    task = session.scalar(stmt)
    if task is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return task
