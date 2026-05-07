import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import PipelineStage, ResearchTask, RunLog, StageStatus, TaskStatus
from app.reports.exporter import export_task_reports

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


PIPELINE_BLUEPRINT = [
    {"key": "discovery", "title": "Discovery", "phase": "Phase 1 - Research", "order": 1, "kind": "work"},
    {"key": "discovery_qc", "title": "Discovery QC", "phase": "Phase 1 - Research", "order": 2, "kind": "qc"},
    {"key": "deep_research", "title": "Deep Research", "phase": "Phase 1 - Research", "order": 3, "kind": "work"},
    {"key": "deep_research_qc", "title": "Deep Research QC", "phase": "Phase 1 - Research", "order": 4, "kind": "qc"},
    {"key": "report_writing", "title": "Report Writing", "phase": "Phase 2 - Writing & Editorial", "order": 5, "kind": "work"},
    {"key": "report_qc", "title": "Report QC (Writers Room)", "phase": "Phase 2 - Writing & Editorial", "order": 6, "kind": "qc"},
    {"key": "humanize_publish", "title": "Humanize & Publish", "phase": "Phase 3 - Polish & Publish", "order": 7, "kind": "work"},
    {"key": "human_review_gate", "title": "Human Review Gate", "phase": "Phase 3 - Polish & Publish", "order": 8, "kind": "gate"},
    {"key": "html_design", "title": "HTML Design", "phase": "Phase 4 - Optional HTML Design", "order": 9, "kind": "work"},
    {"key": "html_design_qc", "title": "HTML Design QC", "phase": "Phase 4 - Optional HTML Design", "order": 10, "kind": "qc"},
]


def log_task(session: Session, task_id: int, message: str, level: str = "info", **metadata: object) -> None:
    session.add(RunLog(task_id=task_id, level=level, message=message, metadata_json=metadata))
    session.commit()


class PipelineModel:
    def __init__(self, settings: Settings):
        self.settings = settings

    def json_response(self, *, prompt: str, use_web_search: bool) -> dict[str, Any]:
        raise NotImplementedError

    def text_response(self, *, prompt: str, use_web_search: bool, model: str | None = None) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIResponsesModel(PipelineModel):
    def __init__(self, settings: Settings):
        super().__init__(settings)
        if OpenAI is None:
            raise RuntimeError("The openai package is not installed")
        self.client = OpenAI(api_key=settings.openai_api_key)

    def json_response(self, *, prompt: str, use_web_search: bool) -> dict[str, Any]:
        response = self._request(prompt=prompt, use_web_search=use_web_search, model=self.settings.openai_model)
        text = response["text"]
        return {
            "data": _extract_json(text),
            "response_id": response["response_id"],
            "sources": response["sources"],
            "text": text,
        }

    def text_response(self, *, prompt: str, use_web_search: bool, model: str | None = None) -> dict[str, Any]:
        response = self._request(prompt=prompt, use_web_search=use_web_search, model=model or self.settings.openai_review_model)
        return {
            "text": response["text"],
            "response_id": response["response_id"],
            "sources": response["sources"],
        }

    def _request(self, *, prompt: str, use_web_search: bool, model: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "input": prompt,
            "reasoning": {"effort": self.settings.openai_reasoning_effort},
        }
        if use_web_search:
            kwargs["tools"] = [
                {
                    "type": "web_search",
                    "user_location": {
                        "type": "approximate",
                        "country": "US",
                        "timezone": "America/New_York",
                    },
                }
            ]
            kwargs["tool_choice"] = "auto"
            kwargs["include"] = ["web_search_call.action.sources"]
        response = self.client.responses.create(**kwargs)
        payload = response.model_dump() if hasattr(response, "model_dump") else {}
        return {
            "response_id": getattr(response, "id", None),
            "text": getattr(response, "output_text", "") or _fallback_output_text(payload),
            "sources": _collect_sources(payload),
        }


class MockPipelineModel(PipelineModel):
    def json_response(self, *, prompt: str, use_web_search: bool) -> dict[str, Any]:
        data: dict[str, Any]
        if "DISCOVERY_QC" in prompt:
            data = {"passed": True, "summary": "Sources and quotes look consistent.", "issues": []}
        elif "DEEP_RESEARCH_QC" in prompt:
            data = {"passed": True, "summary": "Enrichment depth is acceptable.", "issues": []}
        elif "REPORT_QC" in prompt:
            data = {
                "passed": True,
                "summary": "Writers room approved publication.",
                "reviewers": [
                    {"role": "Investigative Journalist", "vote": "publish", "note": "Claims are grounded."},
                    {"role": "Research Analyst", "vote": "publish", "note": "Coverage is balanced."},
                    {"role": "Narrative Architect", "vote": "publish", "note": "Structure is coherent."},
                    {"role": "Prose Stylist", "vote": "publish", "note": "Tone is readable."},
                    {"role": "Executive Reader", "vote": "publish", "note": "Takeaways are clear."},
                ],
            }
        elif "HTML_DESIGN_QC" in prompt:
            data = {"passed": True, "summary": "HTML layout is consistent and readable.", "issues": []}
        elif "DEEP_RESEARCH" in prompt:
            data = {
                "enriched_findings": [
                    {
                        "finding_id": "F1",
                        "strategic_context": "Demand is being driven by cost pressure and platform consolidation.",
                        "competitive_context": "Regional incumbents are pairing delivery with managed services.",
                        "quantitative_evidence": "Analyst notes point to rising spend concentration in fewer strategic vendors.",
                        "source_url": "https://example.com/deep-research",
                    }
                ]
            }
        else:
            data = {
                "findings": [
                    {
                        "id": "F1",
                        "question": "What is changing in the market?",
                        "entity": "Global market",
                        "claim": "Buyers are consolidating around fewer high-trust vendors.",
                        "evidence_quote": "Customers are reducing the number of strategic suppliers they manage.",
                        "source_title": "Example analysis",
                        "source_url": "https://example.com/discovery",
                        "why_it_matters": "This affects vendor strategy and account prioritization.",
                    }
                ],
                "search_queries": ["market consolidation strategic suppliers"],
            }
        return {"data": data, "response_id": "mock-response", "sources": [{"url": "https://example.com"}], "text": json.dumps(data)}

    def text_response(self, *, prompt: str, use_web_search: bool, model: str | None = None) -> dict[str, Any]:
        if "HUMANIZE_PUBLISH" in prompt:
            text = "# Final Report\n\nThis is a polished report ready for review."
        elif "HTML_DESIGN" in prompt:
            text = "<section><h1>Interactive Report</h1><p>Ready for design review.</p></section>"
        else:
            text = "# Research Report\n\nThis is a draft report generated in mock mode."
        return {"text": text, "response_id": "mock-response", "sources": [{"url": "https://example.com"}]}


def get_pipeline_model(settings: Settings | None = None) -> PipelineModel:
    settings = settings or get_settings()
    if settings.openai_api_key:
        return OpenAIResponsesModel(settings)
    return MockPipelineModel(settings)


def run_research_task(session: Session, task: ResearchTask, model: PipelineModel | None = None) -> ResearchTask:
    settings = get_settings()
    model = model or get_pipeline_model(settings)
    task.status = TaskStatus.running.value
    task.locked_at = datetime.now(UTC)
    task.error_message = None
    session.commit()
    log_task(session, task.id, "Research run started", current_stage=task.current_stage)

    try:
        if task.current_stage == "html_design":
            _run_html_design_flow(session, task, model)
        else:
            _run_primary_flow(session, task, model)
        return task
    except Exception as exc:
        session.rollback()
        attached = session.get(ResearchTask, task.id)
        if attached is not None:
            attached.status = TaskStatus.failed.value
            attached.error_message = str(exc)
            attached.locked_at = None
            session.commit()
        log_task(session, task.id, "Research run failed", level="error", error=str(exc))
        raise


def approve_task(session: Session, task: ResearchTask, *, start_html_design: bool) -> ResearchTask:
    gate_stage = _create_stage_record(session, task, "human_review_gate")
    gate_stage.status = StageStatus.completed.value
    gate_stage.summary = "Human reviewer approved the run."
    gate_stage.completed_at = datetime.now(UTC)

    if start_html_design:
        task.html_requested = True
        task.status = TaskStatus.queued.value
        task.current_stage = "html_design"
        task.error_message = None
        log_task(session, task.id, "Human reviewer approved and requested HTML design")
    else:
        task.status = TaskStatus.completed.value
        task.current_stage = "human_review_gate"
        log_task(session, task.id, "Human reviewer approved without HTML design")
    session.commit()
    session.refresh(task)
    return task


def rerun_task(session: Session, task: ResearchTask) -> ResearchTask:
    session.execute(delete(PipelineStage).where(PipelineStage.task_id == task.id))
    task.status = TaskStatus.queued.value
    task.current_stage = None
    task.search_queries = []
    task.pipeline_state = {}
    task.report_paths = {}
    task.final_report_markdown = None
    task.final_report_html = None
    task.error_message = None
    session.commit()
    session.refresh(task)
    return task


def _run_primary_flow(session: Session, task: ResearchTask, model: PipelineModel) -> None:
    discovery_payload = _run_discovery_with_qc(session, task, model)
    deep_payload = _run_deep_research_with_qc(session, task, model, discovery_payload)
    report_payload = _run_report_with_qc(session, task, model, discovery_payload, deep_payload)
    publish_payload = _run_humanize_publish(session, task, model, report_payload)
    _run_human_gate(session, task, publish_payload)


def _run_html_design_flow(session: Session, task: ResearchTask, model: PipelineModel) -> None:
    html_stage = _create_stage_record(session, task, "html_design")
    html_prompt = _html_design_prompt(task)
    html_response = model.text_response(prompt=html_prompt, use_web_search=False, model=get_settings().openai_model)
    html_stage.payload_json = {"html": html_response["text"], "sources": html_response["sources"]}
    html_stage.summary = "Generated interactive HTML from the approved report."
    html_stage.status = StageStatus.completed.value
    html_stage.completed_at = datetime.now(UTC)
    task.final_report_html = html_response["text"]
    session.commit()

    qc_stage = _create_stage_record(session, task, "html_design_qc")
    qc_prompt = _html_design_qc_prompt(task, html_response["text"])
    qc_response = model.json_response(prompt=qc_prompt, use_web_search=False)
    qc_stage.payload_json = qc_response["data"]
    qc_stage.summary = str(qc_response["data"].get("summary", "HTML design reviewed"))
    qc_stage.status = StageStatus.completed.value if qc_response["data"].get("passed") else StageStatus.failed.value
    qc_stage.completed_at = datetime.now(UTC)
    task.status = TaskStatus.completed.value
    task.current_stage = "html_design_qc"
    task.locked_at = None
    task.last_run_at = datetime.now(UTC)
    task.next_run_at = _next_run_time(task)
    task.report_paths = export_task_reports(session, task)
    session.commit()


def _run_discovery_with_qc(session: Session, task: ResearchTask, model: PipelineModel) -> dict[str, Any]:
    settings = get_settings()
    remediation_note = ""
    discovery_payload: dict[str, Any] = {}
    qc_payload: dict[str, Any] = {}
    for attempt in range(1, settings.max_qc_retries + 1):
        discovery_stage = _create_stage_record(session, task, "discovery", attempt=attempt)
        discovery_response = model.json_response(prompt=_discovery_prompt(task, remediation_note), use_web_search=True)
        discovery_payload = discovery_response["data"]
        discovery_payload["sources"] = discovery_response["sources"]
        discovery_stage.payload_json = discovery_payload
        discovery_stage.summary = f"Collected {len(discovery_payload.get('findings', []))} sourced findings."
        discovery_stage.status = StageStatus.completed.value
        discovery_stage.completed_at = datetime.now(UTC)
        task.search_queries = discovery_payload.get("search_queries", [])
        session.commit()

        qc_stage = _create_stage_record(session, task, "discovery_qc", attempt=attempt)
        qc_response = model.json_response(prompt=_discovery_qc_prompt(task, discovery_payload), use_web_search=True)
        qc_payload = qc_response["data"]
        qc_stage.payload_json = qc_payload
        qc_stage.summary = str(qc_payload.get("summary", "Discovery QC complete"))
        qc_stage.status = StageStatus.completed.value if qc_payload.get("passed") else StageStatus.failed.value
        qc_stage.completed_at = datetime.now(UTC)
        session.commit()
        if qc_payload.get("passed"):
            return discovery_payload
        remediation_note = f"QC issues to fix: {json.dumps(qc_payload.get('issues', []), ensure_ascii=False)}"
    raise RuntimeError("Discovery QC failed after maximum retry attempts")


def _run_deep_research_with_qc(
    session: Session,
    task: ResearchTask,
    model: PipelineModel,
    discovery_payload: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    remediation_note = ""
    deep_payload: dict[str, Any] = {}
    qc_payload: dict[str, Any] = {}
    for attempt in range(1, settings.max_qc_retries + 1):
        deep_stage = _create_stage_record(session, task, "deep_research", attempt=attempt)
        deep_response = model.json_response(
            prompt=_deep_research_prompt(task, discovery_payload, remediation_note),
            use_web_search=True,
        )
        deep_payload = deep_response["data"]
        deep_payload["sources"] = deep_response["sources"]
        deep_stage.payload_json = deep_payload
        deep_stage.summary = f"Enriched {len(deep_payload.get('enriched_findings', []))} findings."
        deep_stage.status = StageStatus.completed.value
        deep_stage.completed_at = datetime.now(UTC)
        session.commit()

        qc_stage = _create_stage_record(session, task, "deep_research_qc", attempt=attempt)
        qc_response = model.json_response(
            prompt=_deep_research_qc_prompt(task, discovery_payload, deep_payload),
            use_web_search=True,
        )
        qc_payload = qc_response["data"]
        qc_stage.payload_json = qc_payload
        qc_stage.summary = str(qc_payload.get("summary", "Deep research QC complete"))
        qc_stage.status = StageStatus.completed.value if qc_payload.get("passed") else StageStatus.failed.value
        qc_stage.completed_at = datetime.now(UTC)
        session.commit()
        if qc_payload.get("passed"):
            return deep_payload
        remediation_note = f"QC issues to fix: {json.dumps(qc_payload.get('issues', []), ensure_ascii=False)}"
    raise RuntimeError("Deep Research QC failed after maximum retry attempts")


def _run_report_with_qc(
    session: Session,
    task: ResearchTask,
    model: PipelineModel,
    discovery_payload: dict[str, Any],
    deep_payload: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    report_payload: dict[str, Any] = {}
    qc_payload: dict[str, Any] = {}
    editorial_notes = ""
    for attempt in range(1, settings.max_qc_retries + 1):
        writing_stage = _create_stage_record(session, task, "report_writing", attempt=attempt)
        report_response = model.text_response(
            prompt=_report_writing_prompt(task, discovery_payload, deep_payload, editorial_notes),
            use_web_search=False,
            model=settings.openai_model,
        )
        report_payload = {"markdown": report_response["text"], "sources": report_response["sources"]}
        writing_stage.payload_json = report_payload
        writing_stage.summary = "Drafted the narrative report."
        writing_stage.status = StageStatus.completed.value
        writing_stage.completed_at = datetime.now(UTC)
        task.final_report_markdown = report_response["text"]
        session.commit()

        qc_stage = _create_stage_record(session, task, "report_qc", attempt=attempt)
        qc_response = model.json_response(
            prompt=_report_qc_prompt(task, report_payload["markdown"]),
            use_web_search=False,
        )
        qc_payload = qc_response["data"]
        qc_stage.payload_json = qc_payload
        qc_stage.summary = str(qc_payload.get("summary", "Report QC complete"))
        qc_stage.status = StageStatus.completed.value if qc_payload.get("passed") else StageStatus.failed.value
        qc_stage.completed_at = datetime.now(UTC)
        session.commit()
        if qc_payload.get("passed"):
            return report_payload
        editorial_notes = f"Editorial rewrite notes: {json.dumps(qc_payload, ensure_ascii=False)}"
    raise RuntimeError("Report QC failed after maximum retry attempts")


def _run_humanize_publish(
    session: Session,
    task: ResearchTask,
    model: PipelineModel,
    report_payload: dict[str, Any],
) -> dict[str, Any]:
    publish_stage = _create_stage_record(session, task, "humanize_publish")
    response = model.text_response(
        prompt=_humanize_publish_prompt(task, report_payload["markdown"]),
        use_web_search=False,
        model=get_settings().openai_model,
    )
    html = _markdown_to_html(response["text"])
    payload = {"markdown": response["text"], "html": html, "sources": response["sources"]}
    publish_stage.payload_json = payload
    publish_stage.summary = "Polished the report and prepared publish-ready HTML."
    publish_stage.status = StageStatus.completed.value
    publish_stage.completed_at = datetime.now(UTC)
    task.final_report_markdown = response["text"]
    task.final_report_html = html
    session.commit()
    return payload


def _run_human_gate(session: Session, task: ResearchTask, publish_payload: dict[str, Any]) -> None:
    gate_stage = _create_stage_record(session, task, "human_review_gate")
    gate_stage.payload_json = {
        "status": "awaiting_review",
        "report_ready": bool(task.final_report_markdown),
        "html_requested": task.html_requested,
        "preview_html": publish_payload.get("html"),
    }
    gate_stage.summary = "Pipeline paused for human approval."
    gate_stage.status = StageStatus.awaiting_approval.value
    gate_stage.completed_at = datetime.now(UTC)
    task.status = TaskStatus.awaiting_review.value
    task.current_stage = "human_review_gate"
    task.locked_at = None
    task.last_run_at = datetime.now(UTC)
    task.next_run_at = _next_run_time(task)
    task.report_paths = export_task_reports(session, task)
    session.commit()


def _create_stage_record(session: Session, task: ResearchTask, stage_key: str, attempt: int | None = None) -> PipelineStage:
    blueprint = next(item for item in PIPELINE_BLUEPRINT if item["key"] == stage_key)
    task.current_stage = stage_key
    if attempt is None:
        last_attempt = session.scalar(
            select(func.max(PipelineStage.attempt)).where(
                PipelineStage.task_id == task.id,
                PipelineStage.stage_key == stage_key,
            )
        )
        attempt = (last_attempt or 0) + 1
    stage = PipelineStage(
        task_id=task.id,
        stage_key=stage_key,
        stage_title=str(blueprint["title"]),
        phase=str(blueprint["phase"]),
        stage_order=int(blueprint["order"]),
        stage_kind=str(blueprint["kind"]),
        attempt=attempt,
        status=StageStatus.running.value,
        started_at=datetime.now(UTC),
    )
    session.add(stage)
    session.commit()
    session.refresh(stage)
    return stage


def _next_run_time(task: ResearchTask) -> datetime | None:
    if not task.run_interval_minutes:
        return None
    return datetime.now(UTC) + timedelta(minutes=task.run_interval_minutes)


def _task_context(task: ResearchTask) -> str:
    return json.dumps(
        {
            "title": task.title,
            "brief": task.brief,
            "research_questions": task.research_questions,
            "entities": task.entities,
            "focus_areas": task.focus_areas,
            "report_type": task.report_type,
            "output_language": task.output_language,
            "max_findings": task.max_findings,
            "search_depth": task.search_depth,
        },
        ensure_ascii=False,
        indent=2,
    )


def _discovery_prompt(task: ResearchTask, remediation_note: str) -> str:
    return f"""
STAGE: DISCOVERY

You are the discovery researcher for a multi-stage research pipeline.
Use web search to gather sourced findings for the brief below.
Return strict JSON only with this shape:
{{
  "search_queries": ["..."],
  "findings": [
    {{
      "id": "F1",
      "question": "...",
      "entity": "...",
      "claim": "...",
      "evidence_quote": "...",
      "source_title": "...",
      "source_url": "...",
      "why_it_matters": "..."
    }}
  ]
}}

Requirements:
- Produce up to {task.max_findings} findings.
- Every finding must include a public source URL.
- Evidence quotes must be short and verbatim.
- Cover the listed questions before adding extra findings.
- Prefer credible, recent, public sources.
- Keep claims concrete.

Run context:
{_task_context(task)}

Remediation note:
{remediation_note or "None"}
""".strip()


def _discovery_qc_prompt(task: ResearchTask, discovery_payload: dict[str, Any]) -> str:
    return f"""
STAGE: DISCOVERY_QC

Audit the discovery output using web search. Verify source existence, quote fidelity, topic coverage, and fabrication risk.
Return strict JSON only:
{{
  "passed": true,
  "summary": "...",
  "issues": [
    {{
      "finding_id": "F1",
      "severity": "high|medium|low",
      "issue": "...",
      "recommended_fix": "..."
    }}
  ]
}}

Context:
{_task_context(task)}

Discovery payload:
{json.dumps(discovery_payload, ensure_ascii=False)}
""".strip()


def _deep_research_prompt(task: ResearchTask, discovery_payload: dict[str, Any], remediation_note: str) -> str:
    return f"""
STAGE: DEEP_RESEARCH

Use web search to enrich each discovery finding with deeper context.
Return strict JSON only:
{{
  "enriched_findings": [
    {{
      "finding_id": "F1",
      "strategic_context": "...",
      "competitive_context": "...",
      "quantitative_evidence": "...",
      "source_url": "..."
    }}
  ]
}}

Requirements:
- Add strategic context, competitive context, and at least one quantitative angle whenever available.
- Use public sources only.
- Avoid repeating the discovery quote verbatim unless needed.

Run context:
{_task_context(task)}

Discovery payload:
{json.dumps(discovery_payload, ensure_ascii=False)}

Remediation note:
{remediation_note or "None"}
""".strip()


def _deep_research_qc_prompt(task: ResearchTask, discovery_payload: dict[str, Any], deep_payload: dict[str, Any]) -> str:
    return f"""
STAGE: DEEP_RESEARCH_QC

Audit the enrichment quality. Check for fabricated attributions, shallow competitive analysis, weak quantification, and drift from the original finding.
Return strict JSON only:
{{
  "passed": true,
  "summary": "...",
  "issues": [
    {{
      "finding_id": "F1",
      "severity": "high|medium|low",
      "issue": "...",
      "recommended_fix": "..."
    }}
  ]
}}

Run context:
{_task_context(task)}

Discovery payload:
{json.dumps(discovery_payload, ensure_ascii=False)}

Deep research payload:
{json.dumps(deep_payload, ensure_ascii=False)}
""".strip()


def _report_writing_prompt(
    task: ResearchTask,
    discovery_payload: dict[str, Any],
    deep_payload: dict[str, Any],
    editorial_notes: str,
) -> str:
    return f"""
STAGE: REPORT_WRITING

Write a publishable {task.report_type} in {task.output_language}.
Output markdown only.

Requirements:
- Start with a strong executive summary.
- Organize sections around the research questions.
- Cite finding IDs inline like [F1].
- Convert raw findings into narrative, analysis, and implications.
- Avoid bullet-only dumping.

Run context:
{_task_context(task)}

Discovery payload:
{json.dumps(discovery_payload, ensure_ascii=False)}

Deep research payload:
{json.dumps(deep_payload, ensure_ascii=False)}

Editorial notes:
{editorial_notes or "None"}
""".strip()


def _report_qc_prompt(task: ResearchTask, markdown: str) -> str:
    return f"""
STAGE: REPORT_QC

Act as a writers room with these reviewers:
- Investigative Journalist
- Research Analyst
- Narrative Architect
- Prose Stylist
- Executive Reader

Evaluate the draft and return strict JSON only:
{{
  "passed": true,
  "summary": "...",
  "reviewers": [
    {{
      "role": "...",
      "vote": "publish|revise",
      "note": "..."
    }}
  ]
}}

Publish requires every reviewer to vote publish.

Run context:
{_task_context(task)}

Draft markdown:
{markdown}
""".strip()


def _humanize_publish_prompt(task: ResearchTask, markdown: str) -> str:
    return f"""
STAGE: HUMANIZE_PUBLISH

Rewrite this report to feel more human, specific, and editorial without changing its factual claims.
Output markdown only.

Requirements:
- Remove generic AI patterns and repetitive sentence shapes.
- Preserve finding IDs and factual meaning.
- Keep the structure clear for executive readers.

Run context:
{_task_context(task)}

Draft markdown:
{markdown}
""".strip()


def _html_design_prompt(task: ResearchTask) -> str:
    return f"""
STAGE: HTML_DESIGN

Convert the approved markdown report into a single responsive HTML fragment suitable for a Lovable-style dashboard.
Use semantic sections, data cards, and citation callouts.
Output HTML only.

Run context:
{_task_context(task)}

Approved markdown:
{task.final_report_markdown or ""}
""".strip()


def _html_design_qc_prompt(task: ResearchTask, html: str) -> str:
    return f"""
STAGE: HTML_DESIGN_QC

Review the HTML for clarity, responsiveness, accessibility, and fidelity to the approved report.
Return strict JSON only:
{{
  "passed": true,
  "summary": "...",
  "issues": [
    {{
      "severity": "high|medium|low",
      "issue": "...",
      "recommended_fix": "..."
    }}
  ]
}}

Run context:
{_task_context(task)}

HTML:
{html}
""".strip()


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def _fallback_output_text(payload: dict[str, Any]) -> str:
    output = payload.get("output", [])
    fragments: list[str] = []
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                fragments.append(content["text"])
    return "\n".join(fragments)


def _collect_sources(payload: dict[str, Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for item in payload.get("output", []):
        if item.get("type") != "web_search_call":
            continue
        action = item.get("action") or {}
        for source in action.get("sources", []):
            url = source.get("url")
            if not url:
                continue
            sources.append({"url": url, "title": source.get("title", url)})
    return _dedupe_sources(sources)


def _dedupe_sources(sources: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in sources:
        url = source.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(source)
    return deduped


def _markdown_to_html(markdown: str) -> str:
    blocks = [block.strip() for block in markdown.split("\n\n") if block.strip()]
    html_parts: list[str] = []
    for block in blocks:
        if block.startswith("### "):
            html_parts.append(f"<h3>{block[4:].strip()}</h3>")
        elif block.startswith("## "):
            html_parts.append(f"<h2>{block[3:].strip()}</h2>")
        elif block.startswith("# "):
            html_parts.append(f"<h1>{block[2:].strip()}</h1>")
        elif block.startswith("- "):
            items = [line[2:].strip() for line in block.splitlines() if line.startswith("- ")]
            html_parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>")
        else:
            html_parts.append(f"<p>{block}</p>")
    return "<article>" + "".join(html_parts) + "</article>"
