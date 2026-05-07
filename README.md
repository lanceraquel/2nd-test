# Atlas Research Pipeline

OpenAI-based research agent backend built for Railway deployment. The app turns a research brief into a staged run that follows the Atlas pipeline:

1. Discovery
2. Discovery QC
3. Deep Research
4. Deep Research QC
5. Report Writing
6. Report QC
7. Humanize & Publish
8. Human Review Gate
9. HTML Design (optional after approval)
10. HTML Design QC

The pipeline replaces the old lead-generation placeholder with an explicit research-run workflow, stage records, report artifacts, and a human approval gate.

## What changed

- Uses the OpenAI Responses API for research, QC, writing, and HTML generation.
- Uses OpenAI web search during the research and QC stages.
- Falls back to deterministic mock mode when `OPENAI_API_KEY` is not set, so local tests and Railway smoke checks still work.
- Persists per-stage payloads for dashboard inspection.
- Exposes approval and optional HTML design as first-class run actions.
- Generates JSON, Markdown, HTML, and DOCX artifacts automatically.

## API

- `POST /runs` or `POST /tasks`
- `GET /runs`
- `GET /runs/{id}`
- `POST /runs/{id}/run`
- `POST /runs/{id}/approve`
- `POST /runs/{id}/reports`
- `GET /runs/{id}/reports/latest.docx`
- `GET /health`
- `GET /dashboard`

## Environment

Copy `.env.example` to `.env` and set:

```text
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/atlas_pipeline
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.5
OPENAI_REVIEW_MODEL=gpt-5
OPENAI_REASONING_EFFORT=medium
MAX_QC_RETRIES=5
WORKER_POLL_INTERVAL_SECONDS=15
DEFAULT_MAX_FINDINGS=8
REPORT_OUTPUT_DIR=reports
APP_BASE_URL=http://localhost:8000
```

If `OPENAI_API_KEY` is blank, the worker runs in mock mode and still exercises the full stage lifecycle.

## Local run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run the worker in another terminal:

```bash
python -m app.worker
```

Create a sample run:

```bash
curl -X POST http://localhost:8000/runs ^
  -H "Content-Type: application/json" ^
  --data @sample_task.json
```

Approve a completed run for optional HTML design:

```bash
curl -X POST http://localhost:8000/runs/1/approve ^
  -H "Content-Type: application/json" ^
  -d "{\"start_html_design\": true}"
```

## Railway

Backend service:

```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Worker service:

```bash
python -m app.worker
```

One-shot cron runner:

```bash
python -m app.run_pending_tasks
```

Recommended Railway setup:

1. Create a GitHub-backed Railway project for the backend.
2. Add PostgreSQL.
3. Set the environment variables above on both the API and worker services.
4. Deploy the API and worker as separate Railway services.
5. Point the Vite dashboard at the API by setting `VITE_API_URL`.

## Dashboard and Lovable

The matching Vite dashboard lives in `C:\Users\Admin\Downloads\si-research-dashboard-v2\dashboard`.

Use the dashboard for:

- run creation
- stage inspection
- approval actions
- report preview
- Lovable handoff prompt generation

## Tests

```bash
python -m pytest
```
