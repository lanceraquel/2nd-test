import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.logging_config import configure_logging
from app.models import ResearchTask, TaskStatus
from app.research.openai_pipeline import run_research_task

logger = logging.getLogger(__name__)


def claim_next_task(stale_after_minutes: int = 30) -> ResearchTask | None:
    now = datetime.now(UTC)
    stale_before = datetime.now(UTC) - timedelta(minutes=stale_after_minutes)
    with SessionLocal() as session:
        stmt = (
            select(ResearchTask)
            .where(
                (ResearchTask.status == TaskStatus.queued.value)
                | ((ResearchTask.status == TaskStatus.running.value) & (ResearchTask.locked_at < stale_before))
                | ((ResearchTask.status == TaskStatus.completed.value) & (ResearchTask.next_run_at <= now))
            )
            .order_by(ResearchTask.next_run_at.asc().nullsfirst(), ResearchTask.created_at.asc())
            .limit(1)
        )
        task = session.scalar(stmt)
        if task is None:
            return None
        task.status = TaskStatus.running.value
        task.locked_at = datetime.now(UTC)
        session.commit()
        session.refresh(task)
        return task


def process_one_pending_task() -> bool:
    task = claim_next_task()
    if task is None:
        return False
    with SessionLocal() as session:
        attached_task = session.get(ResearchTask, task.id)
        if attached_task is None:
            return False
        run_research_task(session, attached_task)
    return True


def main() -> None:
    configure_logging()
    init_db()
    settings = get_settings()
    logger.info("SI Research Agent worker started")
    while True:
        processed = process_one_pending_task()
        if not processed:
            time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    main()
