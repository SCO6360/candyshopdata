"""Marketing hub API: the same events as marketing_events.json, but pulled over HTTP.

    GET /api/v1/marketing/events?since=2026-03-01T00:00:00Z&per_page=200&page_token=...
    GET /api/v1/marketing/campaigns
    GET /api/v1/marketing/meta

Pagination here uses an opaque `next_page_token` (the support API uses `after_cursor`) - real vendors disagree.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import MKT_DIR
from .support_api import auth

router = APIRouter(prefix="/api/v1/marketing", tags=["marketing"])
_cache: dict[str, tuple[float, dict]] = {}


def _doc() -> dict:
    path = Path(MKT_DIR) / "marketing_events.json"
    if not path.exists():
        raise HTTPException(503, "marketing_events.json not generated yet - run `candy init`")
    mtime = path.stat().st_mtime
    if "doc" not in _cache or _cache["doc"][0] != mtime:
        _cache["doc"] = (mtime, json.loads(path.read_text(encoding="utf-8")))
    return _cache["doc"][1]


def _when(e: dict) -> datetime:
    if "ts" in e:
        return datetime.fromtimestamp(e["ts"] / 1000, tz=timezone.utc)
    return datetime.fromisoformat(e["occurred_at"].replace("Z", "+00:00"))


@router.get("/events", dependencies=[Depends(auth)])
def events(per_page: int = Query(200, ge=1, le=500), page_token: str | None = None, since: str | None = None,
           event_type: str | None = None):
    items = _doc()["events"]
    if since:
        try:
            cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "since must be ISO-8601")
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        items = [e for e in items if _when(e) >= cutoff]
    if event_type:
        items = [e for e in items if e["event_type"] == event_type]
    try:
        offset = int(base64.urlsafe_b64decode(page_token.encode()).decode()) if page_token else 0
    except Exception:
        raise HTTPException(400, "bad page_token")
    chunk = items[offset:offset + per_page]
    more = offset + per_page < len(items)
    token = base64.urlsafe_b64encode(str(offset + per_page).encode()).decode() if more else None
    return {"events": chunk, "next_page_token": token, "total": len(items)}


@router.get("/campaigns", dependencies=[Depends(auth)])
def campaigns():
    return {"campaigns": _doc()["campaigns"]}


@router.get("/meta", dependencies=[Depends(auth)])
def meta():
    return _doc()["export_meta"]
