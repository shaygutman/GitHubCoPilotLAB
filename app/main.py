"""FastAPI app and routes for Regulatory Radar.

Run locally with:  python -m uvicorn app.main:app --reload
"""

import logging
from collections.abc import Callable, Sized
from datetime import date, datetime
from functools import partial

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from app import openfda, portfolio
from app.config import settings
from app.models import Clearance, Product, Recall, Update

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Regulatory Radar",
    description="What is happening in the regulatory world, and what does it mean for our products?",
    version="0.1.0",
)


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": "1.1.0"}


@app.get("/health")
def health() -> dict:
    """Liveness check that also tells you which data mode is active."""
    return {"status": "ok", "mode": settings.openfda_mode}


@app.get("/health/detailed")
def health_detailed() -> JSONResponse:
    """Check local data and fixtures without contacting external services."""
    checks = {
        "products": _check_local_data(portfolio.load_products),
        "updates": _check_local_data(_load_health_updates),
    }
    for endpoint in ("510k", "recall", "classification"):
        checks[f"fixture_{endpoint}"] = _check_local_data(
            partial(openfda.load_fixture_records, endpoint)
        )
    healthy = all(check["status"] == "ok" for check in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "error",
            "mode": settings.openfda_mode,
            "checks": checks,
        },
    )


def _load_health_updates() -> list[Update]:
    if not settings.updates_dir.is_dir():
        raise FileNotFoundError("Updates directory is unavailable.")
    return portfolio.load_updates()


def _check_local_data(loader: Callable[[], Sized]) -> dict[str, str | int]:
    try:
        count = len(loader())
        if count == 0:
            raise ValueError("No records found.")
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError):
        logger.exception("Local health check failed for %s", loader)
        return {"status": "error", "detail": "Local data is missing, unreadable, invalid or empty."}
    return {"status": "ok", "count": count}


@app.get("/products")
def products() -> list[Product]:
    """The Acme MedTech product portfolio."""
    return portfolio.load_products()


@app.get("/products/{product_id}")
def product(product_id: str) -> Product:
    """One product by its id, or 404."""
    for item in portfolio.load_products():
        if item.id == product_id:
            return item
    raise HTTPException(status_code=404, detail=f"No product with id '{product_id}'.")


@app.get("/updates")
def updates(
    jurisdiction: str = Query("", description="FDA or EU; empty for both"),
    tag: str = Query("", description="Keep only updates carrying this tag"),
    since: date | None = Query(None, description="Only updates published on or after YYYY-MM-DD"),
) -> list[Update]:
    """Regulatory updates from data/updates, newest first, with optional filters."""
    items = portfolio.load_updates()
    if jurisdiction:
        items = [u for u in items if u.jurisdiction.lower() == jurisdiction.lower()]
    if tag:
        items = [u for u in items if tag.lower() in [t.lower() for t in u.tags]]
    if since is not None:
        items = [u for u in items if _parse_update_date(u.date) >= since]
    return items


@app.get("/clearances")
def clearances(
    query: str = Query("", description="Words that must all appear in the device name"),
    limit: int = Query(10, ge=1, le=100),
) -> list[Clearance]:
    """Search 510(k) clearances by device name."""
    records = openfda.search_510k(query)
    return [Clearance(**r) for r in records[:limit]]


@app.get("/recalls")
def recalls(
    query: str = Query("", description="Words that must all appear in the product description"),
    since: date | None = Query(None, description="Only recalls initiated on or after YYYY-MM-DD"),
    limit: int = Query(10, ge=1, le=100),
) -> list[Recall]:
    """Search device recalls by product description, optionally from a date onwards."""
    records = openfda.search_recalls(query)
    if since is not None:
        records = [r for r in records if _recall_initiated_on_or_after(r, since)]
    return [Recall(**r) for r in records[:limit]]


def _recall_initiated_on_or_after(record: dict, since: date) -> bool:
    """True when the recall has a valid YYYY-MM-DD initiation date that is not before `since`."""
    try:
        return date.fromisoformat(record.get("event_date_initiated") or "") >= since
    except ValueError:
        return False


def _parse_update_date(value: str) -> date:
    """Front-matter dates are ISO style; accept them with or without dashes."""
    digits = value.replace("-", "")
    try:
        return datetime.strptime(digits, "%Y%m%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Unreadable update date: {value}") from exc
