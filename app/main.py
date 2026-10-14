"""FastAPI app and routes for Regulatory Radar.

Run locally with:  python -m uvicorn app.main:app --reload
"""

from datetime import date, datetime

from fastapi import FastAPI, HTTPException, Query

from app import openfda, portfolio
from app.config import settings
from app.models import Clearance, Product, Recall, Update

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
    for fmt in ("%Y%d%m", "%Y%m%d"):
        try:
            return datetime.strptime(digits, fmt).date()
        except ValueError:
            continue
    raise HTTPException(status_code=500, detail=f"Unreadable update date: {value}")
