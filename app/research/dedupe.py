import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

from app.models import Company
from app.research.extractor import ExtractedLead


LEGAL_SUFFIXES = {"inc", "llc", "ltd", "limited", "corp", "corporation", "co", "company", "pte"}


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_name(name: str) -> str:
    tokens = re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split()
    filtered = [token for token in tokens if token not in LEGAL_SUFFIXES]
    return " ".join(filtered)


def names_match(left: str, right: str, threshold: float = 0.88) -> bool:
    return SequenceMatcher(None, normalize_name(left), normalize_name(right)).ratio() >= threshold


def find_existing_company(lead: ExtractedLead, companies: list[Company]) -> Company | None:
    domain = normalize_domain(lead.website)
    normalized = normalize_name(lead.company_name)
    for company in companies:
        if domain and company.normalized_domain == domain:
            return company
        if lead.linkedin_url and company.linkedin_url == lead.linkedin_url:
            return company
        if company.normalized_name == normalized or names_match(company.name, lead.company_name):
            return company
    return None

