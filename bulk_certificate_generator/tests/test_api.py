import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def app(tmp_path):
    test_app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.sqlite3"),
        "OUTPUT_DIR": str(tmp_path / "certificates"),
        "MAX_RECIPIENTS": 20,
    })
    yield test_app


@pytest.fixture()
def client(app):
    return TestClient(app)


def payload():
    return {
        "event_name": "Python Bootcamp",
        "issue_date": "2026-10-10",
        "recipients": [
            {"name": "Asha Kumar", "email": "asha@example.com"},
            {"name": "Bala Raj", "email": "bala@example.com"},
        ],
    }


def test_create_job_and_generate_certificates(client):
    response = client.post("/api/jobs", json=payload())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["total_count"] == 2
    assert body["success_count"] == 2
    assert body["failure_count"] == 0
    assert all(r["status"] == "success" for r in body["recipients"])


def test_input_validation_rejects_missing_recipients(client):
    response = client.post("/api/jobs", json={"event_name": "Event", "recipients": []})
    assert response.status_code == 400
    assert "recipients" in response.json()["detail"]


def test_invalid_recipient_does_not_block_valid_recipient(client):
    data = payload()
    data["recipients"] = [
        {"name": "Good Recipient", "email": "good@example.com"},
        {"name": "Missing Email"},
    ]
    response = client.post("/api/jobs", json=data)
    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "completed_with_errors"
    assert body["success_count"] == 1
    assert body["failure_count"] == 1
    assert [r["status"] for r in body["recipients"]] == ["success", "failed"]


def test_job_status_endpoint(client):
    created = client.post("/api/jobs", json=payload()).json()
    response = client.get(created["status_url"])
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == created["job_id"]
    assert body["total_count"] == 2
    assert body["success_count"] == 2


def test_individual_generation_failure_does_not_stop_batch(client, app, monkeypatch):
    import app.main as main_module
    real_generator = main_module.generate_certificate
    calls = {"count": 0}

    def fail_first(output_path, recipient_name, course_name, issue_date, certificate_id):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated renderer failure")
        return real_generator(output_path, recipient_name, course_name, issue_date, certificate_id)

    monkeypatch.setattr(main_module, "generate_certificate", fail_first)
    response = client.post("/api/jobs", json=payload())
    body = response.json()
    assert response.status_code == 201
    assert body["success_count"] == 1
    assert body["failure_count"] == 1
    assert body["status"] == "completed_with_errors"


def test_retrieve_generated_pdf(client):
    created = client.post("/api/jobs", json=payload()).json()
    recipient_id = created["recipients"][0]["recipient_id"]
    response = client.get(f"/api/jobs/{created['job_id']}/certificates/{recipient_id}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")


def test_unknown_job_returns_404(client):
    response = client.get("/api/jobs/not-a-real-job")
    assert response.status_code == 404


def test_certificate_for_failed_recipient_is_not_downloadable(client):
    data = payload()
    data["recipients"] = [{"name": "No Email"}]
    created = client.post("/api/jobs", json=data).json()
    recipient_id = created["recipients"][0]["recipient_id"]
    response = client.get(f"/api/jobs/{created['job_id']}/certificates/{recipient_id}")
    assert response.status_code == 409


def test_create_job_has_request_body_in_swagger_schema(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    operation = response.json()["paths"]["/api/jobs"]["post"]
    assert "requestBody" in operation
    assert "application/json" in operation["requestBody"]["content"]
    example = operation["requestBody"]["content"]["application/json"]["examples"]["bulk_job_example"]["value"]
    assert example["event_name"] == "Python Workshop"
    assert len(example["recipients"]) == 2
