from fastapi.testclient import TestClient

from app import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert "cluster" in body
    assert "prometheus" in body


def test_settings_endpoint():
    response = client.get("/api/settings")
    assert response.status_code == 200
    body = response.json()
    assert "pollInterval" in body
    assert "contamination" in body


def test_ai_baseline_collection():
    response = client.post("/api/ai/analyse", json={"cpu": 0.1, "memory": 1.0, "restarts": 0})
    assert response.status_code == 200
    body = response.json()
    assert "trained" in body
    assert "anomaly" in body


def test_analytics_summary_includes_performance_comparison():
    response = client.get("/api/analytics/summary")
    assert response.status_code == 200
    body = response.json()
    assert "performanceComparison" in body
    assert "withHealOps" in body["performanceComparison"]
    assert "withoutHealOps" in body["performanceComparison"]
    assert "estimatedRecoverySuccess" in body


def test_greenops_endpoint_shape():
    response = client.get("/api/analytics/greenops")
    assert response.status_code == 200
    body = response.json()
    assert "available" in body
    assert "wastedCpuCores" in body
    assert "wastedMemoryGb" in body
    assert "estimatedDailyEnergySavingsKwh" in body
