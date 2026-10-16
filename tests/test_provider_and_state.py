import json

import httpx2
from openai import OpenAI
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.skills import Session, SkillClient, _session
from backend.errors import BackendError


QUERY = "Повышение квалификации по Python для сотрудников банка, 72 часа, очно-заочная форма, итоговая аттестация — защита проекта."


def test_cloud_sdk_request_and_real_usage_accounting():
    captured = []
    def handle(request):
        captured.append(request)
        return httpx2.Response(200, json={
            "id": "test-completion", "object": "chat.completion", "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"value": "real-response"}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
        })
    http_client = httpx2.Client(transport=httpx2.MockTransport(handle))
    client = OpenAI(api_key="test-key", base_url="https://foundation-models.api.cloud.ru/v1", http_client=http_client, max_retries=0)
    session = Session(Settings(ml_mode="cloud", cloud_model="test-model"), client, references="REFERENCE_CONTEXT")
    token = _session.set(session)
    try:
        result = SkillClient().generate_json("system", "user", {"value": "fallback"})
        assert result == {"value": "real-response"}
        assert captured[0].url.host == "foundation-models.api.cloud.ru"
        payload = json.loads(captured[0].content)
        assert payload["model"] == "test-model"
        assert '"value": "string"' in payload["messages"][0]["content"]
        assert "REFERENCE_CONTEXT" in payload["messages"][1]["content"]
        assert session.metrics()["total_tokens"] == 25
        assert session.metrics()["api_calls"] == 1
        assert session.metrics()["estimated_cost_rub"] is None
    finally:
        _session.reset(token)
        client.close()


def test_empty_unified_request_is_validation_error(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path / "projects"))) as client:
        assert client.post("/api/v1/evaluate", json={}).status_code == 422


def test_reanalysis_with_missing_information_invalidates_old_skeleton(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "projects"))
    with TestClient(app) as client:
        original = client.post("/api/projects/skeleton", json={"query": QUERY}).json()
        project_id = original["project_id"]
        response = client.post("/api/projects/skeleton", json={"project_id": project_id, "query": "Новый курс"})
        assert response.status_code == 409
        saved = app.state.service.store.load(project_id)
        assert saved.course is None
        assert saved.analysis.is_complete is False


def test_explicit_hours_are_recorded_consistently(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "projects"))
    with TestClient(app) as client:
        response = client.post("/api/projects/skeleton", json={"query": QUERY, "total_hours": 36})
        assert response.status_code == 200, response.text
        record = app.state.service.store.load(response.json()["project_id"])
        assert record.course.total_hours == 36
        assert record.analysis.extracted_params["total_hours"] == 36


def test_balance_cannot_silently_change_attestation_hours(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "projects"))
    with TestClient(app) as client:
        response = client.post("/api/projects/skeleton", json={"query": QUERY, "template_type": "doop", "total_hours": 24})
        assert response.status_code == 200, response.text
        course = response.json()
        url = f"/api/projects/{course['project_id']}"
        response = client.put(url + "/skeleton", json={"ia_hours": 6, "revision": course["revision"]})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "attestation_hours_changed"
        assert client.get(url).json()["status"] == "skeleton_ready"
