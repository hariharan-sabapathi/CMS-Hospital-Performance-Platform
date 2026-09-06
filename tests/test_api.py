"""Integration tests for each read API endpoint, against a fixture database."""

from __future__ import annotations


def test_healthz_never_touches_db(api_client):
    r = api_client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_ok(api_client):
    r = api_client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["row_count"] == 3


def test_hospital_requires_api_key(api_client):
    r = api_client.get("/hospitals/010001")
    assert r.status_code == 401
    body = r.json()
    assert body["type"] == "https://cms-platform.dev/problems/unauthorized"
    assert body["status"] == 401
    assert body["instance"] == "/hospitals/010001"
    assert body["request_id"]
    assert r.headers["content-type"] == "application/problem+json"


def test_get_hospital_profile(api_client):
    r = api_client.get("/hospitals/010001", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    assert "ETag" in r.headers
    body = r.json()
    assert body["ccn"] == "010001"
    assert body["hospital_name"] == "SOUTHEAST HEALTH MEDICAL CENTER"
    assert body["total_performance_score"] == 32.17
    assert body["estimated_dollar_impact_synthetic"] == 0.0
    assert body["payment_adjustment_factor"] is None
    measure_ids = {m["measure_id"] for m in body["measures"]}
    assert "OP_18a" in measure_ids


def test_get_hospital_conditional_request_returns_304(api_client):
    r1 = api_client.get("/hospitals/010001", headers={"X-API-Key": "test-key"})
    etag = r1.headers["ETag"]

    r2 = api_client.get(
        "/hospitals/010001",
        headers={"X-API-Key": "test-key", "If-None-Match": etag},
    )
    assert r2.status_code == 304
    assert r2.headers["ETag"] == etag
    assert r2.text == ""


def test_get_hospital_not_found_returns_rfc7807_404(api_client):
    r = api_client.get("/hospitals/999999", headers={"X-API-Key": "test-key"})
    assert r.status_code == 404
    body = r.json()
    assert body["type"] == "https://cms-platform.dev/problems/hospital-not-found"
    assert body["title"] == "Hospital Not Found"
    assert body["status"] == 404
    assert body["instance"] == "/hospitals/999999"
    assert "request_id" in body
    assert "X-Request-ID" in r.headers


def test_list_hospitals_filters_by_state(api_client):
    r = api_client.get("/hospitals", params={"state": "AL"}, headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["has_more"] is False
    assert body["pagination"]["next_cursor"] is None


def test_list_hospitals_respects_limit_and_returns_next_cursor(api_client):
    r = api_client.get("/hospitals", params={"state": "AL", "limit": 1}, headers={"X-API-Key": "test-key"})
    body = r.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["has_more"] is True
    assert body["pagination"]["next_cursor"] is not None


def test_list_hospitals_cursor_advances_to_next_page(api_client):
    first = api_client.get("/hospitals", params={"state": "AL", "limit": 1}, headers={"X-API-Key": "test-key"})
    cursor = first.json()["pagination"]["next_cursor"]

    second = api_client.get(
        "/hospitals",
        params={"state": "AL", "limit": 1, "cursor": cursor},
        headers={"X-API-Key": "test-key"},
    )
    body = second.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["ccn"] != first.json()["data"][0]["ccn"]
    assert body["pagination"]["has_more"] is False


def test_list_hospitals_no_filter_returns_all(api_client):
    r = api_client.get("/hospitals", headers={"X-API-Key": "test-key"})
    assert len(r.json()["data"]) == 3


def test_list_hospitals_rejects_unwhitelisted_sort_field(api_client):
    r = api_client.get("/hospitals", params={"sort": "payment_adjustment_factor"}, headers={"X-API-Key": "test-key"})
    assert r.status_code == 400
    body = r.json()
    assert body["type"] == "https://cms-platform.dev/problems/invalid-query-parameter"
    assert body["status"] == 400
    assert "allowed" in body


def test_list_hospitals_sort_descending(api_client):
    r = api_client.get(
        "/hospitals",
        params={"sort": "-total_performance_score"},
        headers={"X-API-Key": "test-key"},
    )
    body = r.json()
    scores = [row["total_performance_score"] for row in body["data"]]
    non_null = [s for s in scores if s is not None]
    assert non_null == sorted(non_null, reverse=True)
    # NULLs always sort last, in both directions -- see query_params.order_by_clause.
    assert scores[len(non_null) :] == [None] * (len(scores) - len(non_null))


def test_list_hospitals_pagination_is_complete_with_nullable_sort_field(api_client):
    """mart_ed_performance_vs_hvbp is built with left joins -- present_in_ed/present_in_hvbp exist
    precisely because some hospitals are missing from one side, so total_performance_score is
    nullable. A keyset predicate of `(col, ccn) > (?, ?)` evaluates to SQL NULL (not TRUE) once
    either side is NULL, which silently drops every hospital with a NULL score behind a 200.
    Page all the way through and confirm nothing is lost, in both sort directions."""
    for sort in ("total_performance_score", "-total_performance_score"):
        full = api_client.get(
            "/hospitals", params={"sort": sort, "limit": 500}, headers={"X-API-Key": "test-key"}
        )
        expected_ccns = {row["ccn"] for row in full.json()["data"]}
        assert len(expected_ccns) == 3  # sanity: the fixture has a hospital with a NULL score

        collected: set[str] = set()
        cursor = None
        for _ in range(10):  # generous upper bound -- the bug either loses rows or stalls early
            params = {"sort": sort, "limit": 1}
            if cursor:
                params["cursor"] = cursor
            page = api_client.get("/hospitals", params=params, headers={"X-API-Key": "test-key"})
            body = page.json()
            collected.update(row["ccn"] for row in body["data"])
            if not body["pagination"]["has_more"]:
                break
            cursor = body["pagination"]["next_cursor"]
        else:
            raise AssertionError(f"sort={sort!r}: pagination did not terminate within 10 pages")

        assert collected == expected_ccns, f"sort={sort!r} lost rows: {expected_ccns - collected}"


def test_list_hospitals_conditional_request_returns_304(api_client):
    r1 = api_client.get("/hospitals", params={"state": "AL"}, headers={"X-API-Key": "test-key"})
    etag = r1.headers["ETag"]
    r2 = api_client.get(
        "/hospitals",
        params={"state": "AL"},
        headers={"X-API-Key": "test-key", "If-None-Match": etag},
    )
    assert r2.status_code == 304


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
    assert r.json()["type"] == "https://cms-platform.dev/problems/hospital-not-found"
