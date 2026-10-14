"""Detailed health checks use local data, including in live mode."""

from dataclasses import replace
from shutil import copy2, copytree

import pytest
from fastapi.testclient import TestClient

from app import main, openfda, portfolio

client = TestClient(main.app)


@pytest.fixture
def local_data(tmp_path, monkeypatch):
    settings = main.settings
    copy2(settings.portfolio_path, tmp_path / "portfolio.yaml")
    copytree(settings.updates_dir, tmp_path / "updates")
    copytree(settings.fixtures_dir, tmp_path / "fixtures")
    isolated = replace(
        settings,
        portfolio_path=tmp_path / "portfolio.yaml",
        updates_dir=tmp_path / "updates",
        fixtures_dir=tmp_path / "fixtures",
    )
    for module in (main, portfolio, openfda):
        monkeypatch.setattr(module, "settings", isolated)
    return tmp_path


@pytest.mark.parametrize("mode", ["fixture", "live"])
def test_detailed_health_checks_all_local_components(mode, monkeypatch):
    for module in (main, portfolio, openfda):
        monkeypatch.setattr(module, "settings", replace(module.settings, openfda_mode=mode))

    def reject_network(*args, **kwargs):
        pytest.fail("Detailed health must not make network requests.")

    monkeypatch.setattr(openfda.httpx, "get", reject_network)
    response = client.get("/health/detailed")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == mode
    assert set(body["checks"]) == {
        "products", "updates", "fixture_510k", "fixture_recall", "fixture_classification"
    }
    assert body["checks"]["products"] == {"status": "ok", "count": 6}
    assert all(check["status"] == "ok" and check["count"] > 0 for check in body["checks"].values())


@pytest.mark.parametrize(
    ("path", "component", "content"),
    [
        ("portfolio.yaml", "products", None),
        ("portfolio.yaml", "products", "products: ["),
        ("portfolio.yaml", "products", "products: []"),
        ("portfolio.yaml", "products", "products: [{}]"),
        ("updates/broken.md", "updates", "not valid front matter"),
        ("fixtures/510k.json", "fixture_510k", None),
        ("fixtures/recall.json", "fixture_recall", "{"),
        ("fixtures/classification.json", "fixture_classification", '{"results": []}'),
        ("fixtures/510k.json", "fixture_510k", '{"results": [1]}'),
        ("fixtures/recall.json", "fixture_recall", "{}"),
    ],
)
def test_detailed_health_reports_failed_component(local_data, path, component, content):
    target = local_data / path
    if content is None:
        target.unlink()
    else:
        target.write_text(content, encoding="utf-8")
    response = client.get("/health/detailed")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["checks"][component]["status"] == "error"
    assert body["checks"][component]["detail"]
    assert all(
        check["status"] == "ok"
        for name, check in body["checks"].items()
        if name != component
    )
    assert client.get("/health").json() == {"status": "ok", "mode": "fixture"}


@pytest.mark.parametrize("missing", [False, True])
def test_detailed_health_rejects_empty_or_missing_updates(local_data, monkeypatch, missing):
    updates_dir = local_data / ("missing" if missing else "empty")
    if not missing:
        updates_dir.mkdir()
    for module in (main, portfolio):
        monkeypatch.setattr(module, "settings", replace(module.settings, updates_dir=updates_dir))
    response = client.get("/health/detailed")
    assert response.status_code == 503
    assert response.json()["checks"]["updates"]["status"] == "error"


def test_detailed_health_reports_multiple_failures(local_data):
    (local_data / "portfolio.yaml").unlink()
    (local_data / "fixtures" / "recall.json").unlink()
    response = client.get("/health/detailed")
    assert response.status_code == 503
    checks = response.json()["checks"]
    assert checks["products"]["status"] == checks["fixture_recall"]["status"] == "error"
    assert checks["updates"]["status"] == checks["fixture_510k"]["status"] == "ok"
    assert checks["fixture_classification"]["status"] == "ok"
