"""API tests. They read local data and saved fixtures only; no network is involved."""

from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import _parse_update_date, app
from app.models import Update

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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025-03-04", date(2025, 3, 4)),
        ("20250304", date(2025, 3, 4)),
        ("2025-04-03", date(2025, 4, 3)),
        ("20250403", date(2025, 4, 3)),
        ("2024-02-29", date(2024, 2, 29)),
        ("20240229", date(2024, 2, 29)),
        ("2025-12-31", date(2025, 12, 31)),
        ("20251231", date(2025, 12, 31)),
    ],
)
def test_update_date_parses_year_month_day(value, expected):
    assert _parse_update_date(value) == expected


@pytest.mark.parametrize("value", ["2025-13-01", "20251301", "2025-02-29", "not-a-date"])
def test_update_date_rejects_invalid_dates(value):
    with pytest.raises(HTTPException) as error:
        _parse_update_date(value)
    assert error.value.status_code == 500
    assert error.value.detail == f"Unreadable update date: {value}"


@pytest.mark.parametrize("compact", [False, True])
def test_updates_since_uses_month_day_order_and_includes_boundary(monkeypatch, compact):
    dates = ["2025-04-03", "2025-03-10", "2025-03-04"]
    items = [
        Update(
            id=value,
            title="Date filter regression",
            date=value.replace("-", "") if compact else value,
            jurisdiction="FDA",
            tags=["ai"],
            source_url="https://example.com/update",
            body="",
        )
        for value in dates
    ]
    monkeypatch.setattr("app.main.portfolio.load_updates", lambda: items)
    response = client.get(
        "/updates", params={"since": "2025-03-10", "jurisdiction": "fda", "tag": "AI"}
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["2025-04-03", "2025-03-10"]


@pytest.mark.parametrize("endpoint", ["/updates", "/recalls"])
def test_since_query_rejects_invalid_date(endpoint):
    assert client.get(endpoint, params={"since": "2025-13-01"}).status_code == 422


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
