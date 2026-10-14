"""The only module that fetches data: from api.fda.gov (live) or saved fixtures."""

import json
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import settings

Record = dict[str, Any]

LIVE_PAGE_SIZE = 100  # how many records to ask openFDA for per request


def search_510k(query: str) -> list[Record]:
    """Return raw 510(k) records whose device name contains every word in query."""
    return _search("510k", "device_name", query)


def search_recalls(query: str) -> list[Record]:
    """Return raw recall records whose product description contains every word in query."""
    return _search("recall", "product_description", query)


def _search(endpoint: str, field: str, query: str) -> list[Record]:
    if settings.openfda_mode == "live":
        return _search_live(endpoint, field, query)
    return _search_fixture(endpoint, field, query)


def _search_fixture(endpoint: str, field: str, query: str) -> list[Record]:
    """Filter a saved openFDA response the same way a live search would."""
    records = load_fixture_records(endpoint)
    words = query.lower().split()
    return [r for r in records if all(w in str(r.get(field, "")).lower() for w in words)]


def load_fixture_records(endpoint: str) -> list[Record]:
    """Load and validate the records in a saved openFDA response."""
    path = settings.fixtures_dir / f"{endpoint}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Fixture response must be an object.")
    records = payload.get("results")
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ValueError("Fixture results must be a list of objects.")
    return records


def _search_live(endpoint: str, field: str, query: str) -> list[Record]:
    """Call api.fda.gov and turn network problems into clean HTTP errors."""
    params: dict[str, Any] = {"limit": LIVE_PAGE_SIZE}
    if query.split():
        params["search"] = " AND ".join(f"{field}:{word}" for word in query.split())
    if settings.openfda_api_key:
        params["api_key"] = settings.openfda_api_key
    url = f"{settings.openfda_base_url}/device/{endpoint}.json"

    try:
        response = httpx.get(url, params=params, timeout=settings.openfda_timeout)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="openFDA did not answer in time.")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach openFDA: {exc}")

    if response.status_code == 404:
        return []  # openFDA answers 404 when a search has no matches
    if response.status_code == 403:
        raise HTTPException(status_code=502, detail="openFDA rejected the request; check OPENFDA_API_KEY.")
    if response.status_code != 200:
        raise HTTPException(
            status_code=502, detail=f"openFDA returned HTTP {response.status_code}."
        )
    return response.json().get("results", [])
