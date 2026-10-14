"""API tests. They read local data and saved fixtures only; no network is involved."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_version():
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"version": "1.1.0"}


def test_health_reports_fixture_mode():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "fixture"}


def test_products_list_and_detail():
    items = client.get("/products").json()
    assert len(items) == 6
    assert all(item["product_codes"] for item in items)
    assert all(len(code) == 3 and code.isupper() for item in items for code in item["product_codes"])
    assert client.get("/products/pulse-dr").json()["name"] == "Acme Pulse DR"
    assert client.get("/products/does-not-exist").status_code == 404


def test_updates_filter_by_jurisdiction_and_tag():
    fda = client.get("/updates", params={"jurisdiction": "FDA"}).json()
    assert len(fda) == 4
    assert all(u["jurisdiction"] == "FDA" for u in fda)
    ai = client.get("/updates", params={"tag": "ai"}).json()
    assert len(ai) == 3
    assert all("ai" in u["tags"] for u in ai)


def test_updates_since_drops_older_updates():
    items = client.get("/updates", params={"since": "2025-01-01"}).json()
    assert len(items) == 7
    assert all(u["date"] >= "2025-01-01" for u in items)
    assert "fda-udi-requirements" not in [u["id"] for u in items]


def test_clearances_query_and_limit():
    results = client.get("/clearances", params={"query": "pacemaker", "limit": 3}).json()
    assert len(results) == 3
    assert all("pacemaker" in r["device_name"].lower() for r in results)


def test_recalls_since_keeps_only_newer_recalls():
    params = {"query": "pacemaker", "since": "2017-01-01", "limit": 50}
    results = client.get("/recalls", params=params).json()
    assert len(results) == 6
    assert all(r["event_date_initiated"] >= "2017-01-01" for r in results)
    assert all(r["product_res_number"].startswith("Z-") for r in results)
