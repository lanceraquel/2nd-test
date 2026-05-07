from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session
from app.schemas import HealthRead
from fastapi import Depends

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthRead)
def health(session: Session = Depends(get_session)) -> HealthRead:
    session.execute(text("SELECT 1"))
    return HealthRead(status="ok", database="ok", mode="openai" if get_settings().openai_api_key else "mock")
