import logging
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote_plus

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    query: str


class SearchProvider(Protocol):
    def search(self, query: str, max_results: int) -> list[SearchResult]:
        ...


class StarterSearchProvider:
    """Deterministic provider used until an official search API is configured.

    Future integration point: replace this class with a provider backed by
    Bing Web Search, SerpAPI, Google Programmable Search, or another compliant
    API. Keep credentials in environment variables only.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        vendors = ["Microsoft", "Salesforce", "SAP", "NetSuite", "Odoo", "AWS"]
        services = ["ERP", "CRM", "cloud migration", "cybersecurity", "AI automation"]
        countries = ["Singapore", "Philippines", "Malaysia", "Thailand", "Indonesia", "Vietnam"]
        results: list[SearchResult] = []
        limit = max(1, min(max_results, 6))
        for index in range(limit):
            country = countries[index % len(countries)]
            service = services[index % len(services)]
            vendor = vendors[index % len(vendors)]
            slug = quote_plus(query.lower())
            domain_slug = re.sub(r"[^a-z0-9]+", "-", f"{country}-{service}-{index + 1}".lower()).strip("-")
            name = f"{country} {service.title()} Integration Partners"
            results.append(
                SearchResult(
                    title=name,
                    url=f"https://{domain_slug}.example.com/search-evidence/{slug}",
                    snippet=(
                        f"{name} is described as a systems integrator serving {country} "
                        f"with {service}, implementation, managed services, and {vendor} partner capabilities."
                    ),
                    query=query,
                )
            )
        return results


class SerpApiSearchProvider:
    """Search provider backed by SerpAPI Google Search.

    SerpAPI credentials must be supplied through SEARCH_API_KEY. The key is
    never logged or persisted. See https://serpapi.com/search-api for params.
    """

    endpoint = "https://serpapi.com/search.json"

    def __init__(self, settings: Settings) -> None:
        if not settings.search_api_key:
            raise ValueError("SEARCH_API_KEY is required for SerpAPI")
        self.settings = settings

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        limit = max(1, min(max_results, 10))
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.settings.search_api_key,
            "num": limit,
        }
        headers = {"User-Agent": self.settings.user_agent}
        try:
            response = httpx.get(self.endpoint, params=params, headers=headers, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("SerpAPI request failed for query %r: %s", query, exc)
            raise RuntimeError("SerpAPI request failed; verify SEARCH_API_KEY and account quota") from exc

        payload = response.json()
        if "error" in payload:
            raise RuntimeError(f"SerpAPI returned an error: {payload['error']}")

        organic_results = payload.get("organic_results") or []
        results: list[SearchResult] = []
        for item in organic_results[:limit]:
            url = item.get("link")
            title = item.get("title")
            snippet = item.get("snippet") or ""
            if not snippet and item.get("snippet_highlighted_words"):
                snippet = " ".join(str(word) for word in item["snippet_highlighted_words"])
            if not url or not title:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    query=query,
                )
            )
        return results


def get_search_provider(settings: Settings) -> SearchProvider:
    if settings.search_api_key:
        return SerpApiSearchProvider(settings)
    return StarterSearchProvider(settings)
