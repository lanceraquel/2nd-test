import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.research.search_providers import SearchResult


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}")


@dataclass
class ExtractedLead:
    company_name: str
    website: str | None
    location: str | None
    countries_served: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    vendor_partnerships: list[str] = field(default_factory=list)
    industries_served: list[str] = field(default_factory=list)
    contact_page_url: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    description: str | None = None
    source_urls: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    notes: str | None = None


SERVICE_TERMS = {
    "erp": "ERP",
    "crm": "CRM",
    "cloud": "cloud migration",
    "cybersecurity": "cybersecurity",
    "ai": "AI automation",
    "managed services": "managed services",
    "implementation": "implementation",
}
VENDOR_TERMS = ["Microsoft", "Salesforce", "NetSuite", "SAP", "Odoo", "AWS", "Oracle"]
COUNTRY_TERMS = ["Singapore", "Philippines", "Malaysia", "Thailand", "Indonesia", "Vietnam"]


def extract_lead(result: SearchResult, requested_industry: str) -> ExtractedLead:
    text = f"{result.title} {result.snippet}"
    services = [label for term, label in SERVICE_TERMS.items() if term.lower() in text.lower()]
    vendors = [vendor for vendor in VENDOR_TERMS if vendor.lower() in text.lower()]
    countries = [country for country in COUNTRY_TERMS if country.lower() in text.lower()]
    email_match = EMAIL_RE.search(text)
    phone_match = PHONE_RE.search(text)
    parsed = urlparse(result.url)
    website = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else None
    confidence = 45.0
    confidence += min(len(services) * 7.5, 25.0)
    confidence += min(len(vendors) * 5.0, 15.0)
    confidence += 10.0 if "systems integrator" in text.lower() else 0.0
    confidence = min(confidence, 100.0)
    return ExtractedLead(
        company_name=result.title.replace(" - ", " ").strip(),
        website=website,
        location=countries[0] if countries else None,
        countries_served=countries,
        services=list(dict.fromkeys(services)),
        vendor_partnerships=vendors,
        industries_served=[requested_industry],
        contact_page_url=f"{website}/contact" if website else None,
        linkedin_url=None,
        email=email_match.group(0) if email_match else None,
        phone=phone_match.group(0) if phone_match else None,
        description=result.snippet,
        source_urls=[result.url],
        confidence_score=confidence,
        notes="Likely SI based on search evidence mentioning integration, implementation, services, or vendor partnerships.",
    )

