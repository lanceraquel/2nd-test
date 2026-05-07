from app.models import ResearchTask
from app.research.extractor import ExtractedLead


def score_lead(task: ResearchTask, lead: ExtractedLead) -> dict[str, float]:
    service_matches = set(item.lower() for item in lead.services) & set(item.lower() for item in task.service_categories)
    keyword_matches = set(item.lower() for item in lead.services) & set(item.lower() for item in task.si_keywords)
    geography_match = any(task.target_geography.lower() in country.lower() for country in lead.countries_served)
    geography_match = geography_match or bool(lead.location and lead.location.lower() in task.target_geography.lower())
    industry_match = task.target_industry.lower() in " ".join(lead.industries_served).lower()
    contact_points = sum(bool(value) for value in [lead.contact_page_url, lead.email, lead.phone, lead.linkedin_url])

    breakdown = {
        "si_relevance": 25.0 if "integrator" in (lead.description or "").lower() else 15.0,
        "geography_match": 15.0 if geography_match or lead.countries_served else 6.0,
        "industry_match": 10.0 if industry_match else 4.0,
        "service_match": min(20.0, len(service_matches | keyword_matches) * 5.0 + len(lead.services) * 2.0),
        "vendor_partnerships": min(10.0, len(lead.vendor_partnerships) * 3.0),
        "evidence_quality": min(10.0, len(lead.source_urls) * 4.0 + lead.confidence_score / 25.0),
        "contact_details": min(5.0, contact_points * 1.5),
        "maturity_signals": 5.0 if lead.vendor_partnerships and len(lead.services) >= 2 else 2.0,
    }
    total = min(100.0, round(sum(breakdown.values()), 2))
    breakdown["total"] = total
    return breakdown

