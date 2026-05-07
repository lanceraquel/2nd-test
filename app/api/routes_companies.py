from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_session
from app.models import Company
from app.schemas import CompanyRead

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[CompanyRead])
def list_companies(session: Session = Depends(get_session), limit: int = 100, offset: int = 0) -> list[Company]:
    stmt = (
        select(Company)
        .options(selectinload(Company.sources), selectinload(Company.contacts))
        .order_by(Company.confidence_score.desc(), Company.name.asc())
        .offset(offset)
        .limit(min(limit, 500))
    )
    return list(session.scalars(stmt).all())


@router.get("/{company_id}", response_model=CompanyRead)
def get_company(company_id: int, session: Session = Depends(get_session)) -> Company:
    stmt = (
        select(Company)
        .where(Company.id == company_id)
        .options(selectinload(Company.sources), selectinload(Company.contacts))
    )
    company = session.scalar(stmt)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

