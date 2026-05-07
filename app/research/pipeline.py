import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Company, CompanyContact, CompanySource, ResearchResult, ResearchTask, RunLog, TaskStatus
from app.reports.exporter import export_task_reports
from app.research.dedupe import find_existing_company, normalize_domain, normalize_name
from app.research.extractor import ExtractedLead, extract_lead
from app.research.query_builder import build_queries
from app.research.scorer import score_lead
from app.research.search_providers import SearchProvider, get_search_provider

logger = logging.getLogger(__name__)


def log_task(session: Session, task_id: int, message: str, level: str = "info", **metadata: object) -> None:
    session.add(RunLog(task_id=task_id, level=level, message=message, metadata_json=metadata))
    session.commit()


def _upsert_company(session: Session, lead: ExtractedLead) -> Company:
    companies = list(session.scalars(select(Company).options(selectinload(Company.sources), selectinload(Company.contacts))).all())
    existing = find_existing_company(lead, companies)
    if existing:
        existing.services = list(dict.fromkeys([*existing.services, *lead.services]))
        existing.vendor_partnerships = list(dict.fromkeys([*existing.vendor_partnerships, *lead.vendor_partnerships]))
        existing.countries_served = list(dict.fromkeys([*existing.countries_served, *lead.countries_served]))
        existing.industries_served = list(dict.fromkeys([*existing.industries_served, *lead.industries_served]))
        existing.confidence_score = max(existing.confidence_score, lead.confidence_score)
        company = existing
    else:
        company = Company(
            name=lead.company_name,
            normalized_name=normalize_name(lead.company_name),
            website=lead.website,
            normalized_domain=normalize_domain(lead.website),
            linkedin_url=lead.linkedin_url,
            headquarters=lead.location,
            countries_served=lead.countries_served,
            services=lead.services,
            vendor_partnerships=lead.vendor_partnerships,
            industries_served=lead.industries_served,
            description=lead.description,
            notes=lead.notes,
            confidence_score=lead.confidence_score,
        )
        session.add(company)
        session.flush()

    existing_source_urls = {source.source_url for source in company.sources}
    for url in lead.source_urls:
        if url not in existing_source_urls:
            session.add(CompanySource(company_id=company.id, source_url=url, evidence_text=lead.description))

    if lead.contact_page_url or lead.email or lead.phone:
        has_same_contact = any(
            contact.contact_page_url == lead.contact_page_url and contact.email == lead.email and contact.phone == lead.phone
            for contact in company.contacts
        )
        if not has_same_contact:
            session.add(
                CompanyContact(
                    company_id=company.id,
                    contact_page_url=lead.contact_page_url,
                    email=lead.email,
                    phone=lead.phone,
                )
            )
    return company


def run_research_task(session: Session, task: ResearchTask, provider: SearchProvider | None = None) -> ResearchTask:
    settings = get_settings()
    provider = provider or get_search_provider(settings)
    task_id = task.id
    task.status = TaskStatus.running.value
    task.locked_at = datetime.now(UTC)
    task.error_message = None
    session.commit()
    log_task(session, task.id, "Research task started")

    try:
        queries = build_queries(task)
        task.search_queries = queries
        session.commit()
        leads: list[ExtractedLead] = []
        per_query_limit = max(1, min(task.max_results, settings.default_max_results))

        for query in queries:
            if len(leads) >= task.max_results:
                break
            search_results = provider.search(query, per_query_limit)
            log_task(session, task.id, "Search query executed", query=query, results=len(search_results))
            for result in search_results:
                if len(leads) >= task.max_results:
                    break
                lead = extract_lead(result, task.target_industry)
                haystack = " ".join([lead.company_name, lead.description or "", " ".join(lead.services)]).lower()
                if any(exclusion.lower() in haystack for exclusion in task.exclusion_keywords):
                    continue
                leads.append(lead)

        scored_results_by_company: dict[int, ResearchResult] = {}
        for lead in leads:
            company = _upsert_company(session, lead)
            breakdown = score_lead(task, lead)
            if company.id in scored_results_by_company:
                result = scored_results_by_company[company.id]
                if breakdown["total"] > result.relevance_score:
                    result.relevance_score = breakdown["total"]
                    result.scoring_breakdown = breakdown
                    result.notes = lead.notes
                continue
            existing_result = session.scalar(
                select(ResearchResult).where(
                    ResearchResult.task_id == task.id,
                    ResearchResult.company_id == company.id,
                )
            )
            if existing_result:
                existing_result.relevance_score = breakdown["total"]
                existing_result.scoring_breakdown = breakdown
                result = existing_result
            else:
                result = ResearchResult(
                    task_id=task.id,
                    company_id=company.id,
                    relevance_score=breakdown["total"],
                    scoring_breakdown=breakdown,
                    notes=lead.notes,
                )
                session.add(result)
            scored_results_by_company[company.id] = result

        session.flush()
        ranked = sorted(scored_results_by_company.values(), key=lambda item: item.relevance_score, reverse=True)
        for rank, result in enumerate(ranked, start=1):
            result.rank = rank

        now = datetime.now(UTC)
        task.status = TaskStatus.completed.value
        task.locked_at = None
        task.last_run_at = now
        task.next_run_at = now + timedelta(minutes=task.run_interval_minutes) if task.run_interval_minutes else None
        session.commit()
        task.report_paths = export_task_reports(session, task)
        session.commit()
        log_task(session, task.id, "Research task completed", companies=len(ranked))
        return task
    except Exception as exc:
        session.rollback()
        logger.exception("Research task failed", extra={"task_id": task_id})
        task = session.get(ResearchTask, task_id)
        if task is not None:
            task.status = TaskStatus.failed.value
            task.error_message = str(exc)
            task.locked_at = None
        session.commit()
        log_task(session, task_id, "Research task failed", level="error", error=str(exc))
        raise
