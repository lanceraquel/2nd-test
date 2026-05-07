from fastapi.testclient import TestClient

from app.main import app
from app.worker import process_one_pending_task


def test_run_can_be_created_processed_and_approved():
    client = TestClient(app)
    payload = {
        "title": "AI partnerships market map",
        "brief": "Map the current AI partnerships landscape, demand shifts, competitor positioning, and strategic implications.",
        "research_questions": [
            "What changed in the last 12 months?",
            "Which competitors are most active?",
        ],
        "entities": ["Microsoft", "Google", "Amazon"],
        "focus_areas": ["partner ecosystem", "enterprise demand"],
        "max_findings": 4,
        "html_requested": False,
    }

    create_response = client.post("/runs", json=payload)
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    assert process_one_pending_task() is True

    task_response = client.get(f"/runs/{task_id}")
    assert task_response.status_code == 200
    task = task_response.json()
    assert task["status"] == "awaiting_review"
    assert task["final_report_markdown"]
    assert any(stage["stage_key"] == "human_review_gate" for stage in task["stages"])

    approve_response = client.post(f"/runs/{task_id}/approve", json={"start_html_design": True})
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "queued"

    assert process_one_pending_task() is True

    completed_response = client.get(f"/runs/{task_id}")
    completed = completed_response.json()
    assert completed["status"] == "completed"
    assert completed["final_report_html"]

    report_response = client.post(f"/runs/{task_id}/reports")
    assert report_response.status_code == 200

    docx_response = client.get(f"/runs/{task_id}/reports/latest.docx")
    assert docx_response.status_code == 200
    assert docx_response.content.startswith(b"PK")
