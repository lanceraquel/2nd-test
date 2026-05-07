from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_session
from app.models import PipelineStage, ResearchTask

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, run_id: int | None = None, session: Session = Depends(get_session)) -> HTMLResponse:
    runs = list(
        session.scalars(
            select(ResearchTask).options(selectinload(ResearchTask.stages)).order_by(ResearchTask.created_at.desc()).limit(50)
        ).unique().all()
    )
    selected = next((run for run in runs if run.id == run_id), runs[0] if runs else None)
    total_runs = session.scalar(select(func.count(ResearchTask.id))) or 0
    awaiting_review = session.scalar(select(func.count(ResearchTask.id)).where(ResearchTask.status == "awaiting_review")) or 0
    stage_count = session.scalar(select(func.count(PipelineStage.id))) or 0
    html = _render_dashboard(
        base_url=str(request.base_url).rstrip("/"),
        runs=runs,
        selected=selected,
        total_runs=total_runs,
        awaiting_review=awaiting_review,
        stage_count=stage_count,
    )
    return HTMLResponse(html)


def _render_dashboard(
    *,
    base_url: str,
    runs: list[ResearchTask],
    selected: ResearchTask | None,
    total_runs: int,
    awaiting_review: int,
    stage_count: int,
) -> str:
    selected_stages = sorted(selected.stages, key=lambda stage: (stage.stage_order, stage.attempt)) if selected else []
    run_cards = "".join(_run_card(run) for run in runs) or "<p class='empty'>No runs yet.</p>"
    stage_cards = "".join(_stage_card(stage) for stage in selected_stages) or "<p class='empty'>No stage output yet.</p>"
    markdown_preview = escape((selected.final_report_markdown or "No report generated yet.")[:4000]) if selected else "Select a run."
    approve_button = (
        f"<button onclick='approveRun({selected.id}, false)'>Approve</button>"
        f"<button class='secondary' onclick='approveRun({selected.id}, true)'>Approve + HTML</button>"
        if selected and selected.status == "awaiting_review"
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Atlas Research Pipeline</title>
  <style>
    :root {{
      --bg: #f3efe6;
      --panel: rgba(255,255,255,.84);
      --ink: #1d2533;
      --muted: #667085;
      --line: rgba(29,37,51,.12);
      --blue: #3454d1;
      --amber: #e1a500;
      --green: #2d9f65;
      --rose: #b64357;
      --shadow: 0 24px 60px rgba(29,37,51,.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Aptos", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(52,84,209,.12), transparent 32%),
        radial-gradient(circle at 80% 10%, rgba(225,165,0,.12), transparent 28%),
        var(--bg);
    }}
    header, main {{ padding: 22px clamp(18px, 4vw, 44px); }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: end; }}
    h1, h2, h3 {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 46px); }}
    .subtle {{ color: var(--muted); }}
    .stats, .layout {{ display: grid; gap: 16px; }}
    .stats {{ grid-template-columns: repeat(3, minmax(0, 1fr)); margin-bottom: 16px; }}
    .layout {{ grid-template-columns: 360px 1fr; }}
    .panel {{
      background: var(--panel);
      backdrop-filter: blur(16px);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: 22px;
      overflow: hidden;
    }}
    .panel-head {{
      padding: 16px 18px 12px;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }}
    .panel-body {{ padding: 18px; }}
    .stat strong {{ display: block; font-size: 34px; }}
    .run-list, .stage-list {{ display: grid; gap: 12px; }}
    .run-card, .stage-card {{
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,.72);
    }}
    .stage-card.work {{ border-left: 6px solid rgba(52,84,209,.42); }}
    .stage-card.qc {{ border-left: 6px solid rgba(225,165,0,.48); }}
    .stage-card.gate {{ border-left: 6px solid rgba(45,159,101,.48); }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      background: rgba(52,84,209,.08);
    }}
    pre {{
      white-space: pre-wrap;
      font: 13px/1.5 "Consolas", monospace;
      background: #fbfaf7;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      max-height: 320px;
      overflow: auto;
    }}
    form {{ display: grid; gap: 10px; }}
    input, textarea {{
      width: 100%;
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255,255,255,.9);
      padding: 11px 12px;
    }}
    textarea {{ min-height: 90px; resize: vertical; }}
    button {{
      border: 0;
      border-radius: 999px;
      background: var(--blue);
      color: white;
      padding: 10px 16px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.secondary {{ background: #152238; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    a {{ color: var(--blue); text-decoration: none; }}
    .empty {{ color: var(--muted); }}
    @media (max-width: 980px) {{
      .stats, .layout {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Atlas Research Pipeline</h1>
      <p class="subtle">OpenAI-first staged research runner for Railway deployment and dashboard handoff.</p>
    </div>
    <div class="subtle"><a href="{base_url}/docs">API docs</a> · <a href="{base_url}/health">Health</a></div>
  </header>
  <main>
    <section class="stats">
      <div class="panel stat panel-body"><span class="subtle">Runs</span><strong>{total_runs}</strong></div>
      <div class="panel stat panel-body"><span class="subtle">Awaiting Review</span><strong>{awaiting_review}</strong></div>
      <div class="panel stat panel-body"><span class="subtle">Stage Records</span><strong>{stage_count}</strong></div>
    </section>
    <section class="layout">
      <div class="panel">
        <div class="panel-head"><h2>New Run</h2><span class="subtle">Phase-aligned intake</span></div>
        <div class="panel-body">
          <form id="run-form">
            <input name="title" placeholder="Run title" value="AI partnerships market map">
            <textarea name="brief" placeholder="Research brief">Map the current AI partnerships landscape, key demand shifts, top competitors, and strategic implications for a B2B software company.</textarea>
            <textarea name="research_questions" placeholder="Questions, one per line">What changed in the last 12 months?
Who are the key competitors and what are they emphasizing?
What strategic risks and opportunities matter most?</textarea>
            <textarea name="entities" placeholder="Entities, one per line">Microsoft
Google
Amazon</textarea>
            <textarea name="focus_areas" placeholder="Focus areas, one per line">partner ecosystem
enterprise demand
competitive positioning</textarea>
            <button type="submit">Create Run</button>
          </form>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head"><h2>Runs</h2><span class="subtle">Latest 50</span></div>
        <div class="panel-body run-list">{run_cards}</div>
      </div>
    </section>
    <section class="layout" style="margin-top:16px">
      <div class="panel">
        <div class="panel-head"><h2>Stage Timeline</h2><span class="subtle">{escape(selected.title) if selected else "Select a run"}</span></div>
        <div class="panel-body stage-list">{stage_cards}</div>
      </div>
      <div class="panel">
        <div class="panel-head">
          <h2>Report Preview</h2>
          <div class="actions">
            {approve_button}
            {f'<a href="/runs/{selected.id}/reports/latest.docx">Download DOCX</a>' if selected else ""}
          </div>
        </div>
        <div class="panel-body"><pre>{markdown_preview}</pre></div>
      </div>
    </section>
  </main>
  <script>
    const splitLines = (value) => value.split("\\n").map((item) => item.trim()).filter(Boolean);
    document.querySelector("#run-form").addEventListener("submit", async (event) => {{
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const payload = {{
        title: form.get("title"),
        brief: form.get("brief"),
        research_questions: splitLines(form.get("research_questions") || ""),
        entities: splitLines(form.get("entities") || ""),
        focus_areas: splitLines(form.get("focus_areas") || ""),
        html_requested: false
      }};
      const response = await fetch("/runs", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload)
      }});
      if (!response.ok) {{
        alert("Run creation failed.");
        return;
      }}
      const run = await response.json();
      window.location.href = `/dashboard?run_id=${{run.id}}`;
    }});
    async function approveRun(runId, startHtmlDesign) {{
      await fetch(`/runs/${{runId}}/approve`, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ start_html_design: startHtmlDesign }})
      }});
      window.location.href = `/dashboard?run_id=${{runId}}`;
    }}
  </script>
</body>
</html>"""


def _run_card(run: ResearchTask) -> str:
    return f"""<a class="run-card" href="/dashboard?run_id={run.id}">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:start">
        <div>
          <h3>{escape(run.title)}</h3>
          <p class="subtle">{escape(run.brief[:180])}</p>
        </div>
        <span class="pill">{escape(run.status)}</span>
      </div>
    </a>"""


def _stage_card(stage: PipelineStage) -> str:
    payload_preview = escape(str(stage.payload_json)[:700]) if stage.payload_json else "No payload"
    return f"""<div class="stage-card {escape(stage.stage_kind)}">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
        <strong>{stage.stage_order}. {escape(stage.stage_title)}</strong>
        <span class="pill">{escape(stage.status)} · attempt {stage.attempt}</span>
      </div>
      <p class="subtle">{escape(stage.phase)}</p>
      <p>{escape(stage.summary or "No summary")}</p>
      <pre>{payload_preview}</pre>
    </div>"""
