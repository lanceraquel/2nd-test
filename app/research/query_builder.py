from app.models import ResearchTask


QUERY_TEMPLATES = [
    "systems integrator {industry} {location}",
    "ERP systems integrator {location}",
    "CRM implementation partner {location}",
    "cloud migration systems integrator {location}",
    "cybersecurity systems integrator {location}",
    "Microsoft partner systems integrator {location}",
    "Salesforce implementation partner {location}",
    "NetSuite partner {location}",
    "SAP implementation partner {location}",
    "Odoo partner {location}",
]


def build_queries(task: ResearchTask) -> list[str]:
    context = {
        "industry": task.target_industry,
        "location": task.target_geography,
    }
    queries = [template.format(**context).strip() for template in QUERY_TEMPLATES]
    for keyword in task.si_keywords:
        queries.append(f"{keyword} systems integrator {task.target_geography}".strip())
    return list(dict.fromkeys(queries))

