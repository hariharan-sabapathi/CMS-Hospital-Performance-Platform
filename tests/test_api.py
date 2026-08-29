"""Integration tests for each read API endpoint, against a fixture database."""

from __future__ import annotations


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["row_count"] == 2


def test_hospital_requires_api_key(api_client):
    r = api_client.get("/hospitals/010001")
    assert r.status_code == 401
    assert r.json()["request_id"]


def test_get_hospital_profile(api_client):
    r = api_client.get("/hospitals/010001", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.json()
    assert body["ccn"] == "010001"
    assert body["hospital_name"] == "SOUTHEAST HEALTH MEDICAL CENTER"
    assert body["total_performance_score"] == 32.17
    assert body["estimated_dollar_impact_synthetic"] == 0.0
    assert body["payment_adjustment_factor"] is None
    measure_ids = {m["measure_id"] for m in body["measures"]}
    assert "OP_18a" in measure_ids


def test_get_hospital_not_found_returns_structured_404(api_client):
    r = api_client.get("/hospitals/999999", headers={"X-API-Key": "test-key"})
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "hospital_not_found"
    assert "request_id" in body
    assert "X-Request-ID" in r.headers


def test_list_hospitals_filters_by_state(api_client):
    r = api_client.get("/hospitals", params={"state": "AL"}, headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["results"]) == 2


def test_list_hospitals_respects_limit(api_client):
    r = api_client.get("/hospitals", params={"state": "AL", "limit": 1}, headers={"X-API-Key": "test-key"})
    body = r.json()
    assert len(body["results"]) == 1
    assert body["total"] == 2


def test_list_hospitals_no_filter_returns_all(api_client):
    r = api_client.get("/hospitals", headers={"X-API-Key": "test-key"})
    assert r.json()["total"] == 2


def test_get_peers(api_client):
    r = api_client.get("/hospitals/010001/peers", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.json()
    assert body["ccn"] == "010001"
    assert len(body["state_peers"]) == 1
    assert body["state_peers"][0]["ccn"] == "010005"


def test_peers_not_found(api_client):
    r = api_client.get("/hospitals/999999/peers", headers={"X-API-Key": "test-key"})
    assert r.status_code == 404
