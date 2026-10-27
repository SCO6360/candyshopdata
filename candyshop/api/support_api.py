"""Mock support-desk REST API (Zendesk-style v2), serving the generated JSON documents.

    candy serve-api                      # http://127.0.0.1:8800/docs
    curl -H "Authorization: Bearer demo-token" "http://127.0.0.1:8800/api/v2/tickets?per_page=2"

* Bearer-token auth (env SUPPORT_API_TOKEN, default "demo-token")
* cursor pagination (`meta.after_cursor` / `links.next`), `per_page` <= 100
* incremental sync with `updated_since` (tickets, users, organizations) / `created_since` (comments)
* a simple per-client rate limit that answers 429 + Retry-After, as real vendors do
* data is re-read whenever the JSON files change, so `candy grow` shows up without a restart
"""
from __future__ import annotations

import base64
import json
import os
import random
import time
from collections import deque
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response

from ..config import SUPPORT_API_TOKEN, SUPPORT_DIR

FLAKY = os.environ.get("CANDY_API_FLAKY", "1") != "0"   # set CANDY_API_FLAKY=0 for a perfectly healthy API
RATE_LIMIT = 300        # requests per rolling minute
MAX_PER_PAGE = 100

app = FastAPI(title="SweetReach Support Desk API", version="2.0",
              description="Fake Zendesk-style support API for the SweetReach candy-shop example project.")

_cache: dict[str, tuple[float, list[dict]]] = {}
_hits: dict[str, deque] = {}


def _load(name: str) -> list[dict]:
    path = Path(SUPPORT_DIR) / f"{name}.json"
    if not path.exists():
        raise HTTPException(503, f"{name}.json not generated yet - run `candy init`")
    mtime = path.stat().st_mtime
    cached = _cache.get(name)
    if cached is None or cached[0] != mtime:
        _cache[name] = (mtime, json.loads(path.read_text(encoding="utf-8")))
    return _cache[name][1]


def _flaky() -> dict:
    path = Path(SUPPORT_DIR) / "_api_config.json"
    if not FLAKY or not path.exists():
        return {"error_rate": 0.0, "overlap_rate": 0.0}
    return json.loads(path.read_text())


def auth(request: Request, response: Response, authorization: str | None = Header(default=None)) -> None:
    if authorization != f"Bearer {SUPPORT_API_TOKEN}":
        raise HTTPException(401, "Couldn't authenticate you", headers={"WWW-Authenticate": "Bearer"})
    client = request.client.host if request.client else "unknown"
    q = _hits.setdefault(client, deque())
    now = time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": str(int(60 - (now - q[0])) + 1)})
    q.append(now)
    if random.random() < _flaky()["error_rate"]:   # transient upstream failure, like any real vendor
        code = random.choice([500, 502, 503])
        raise HTTPException(code, "Temporary upstream error, please retry", headers={"Retry-After": str(random.randint(1, 3))})
    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT)
    response.headers["X-RateLimit-Remaining"] = str(RATE_LIMIT - len(q))


def _encode(last_id: int) -> str:
    return base64.urlsafe_b64encode(str(last_id).encode()).decode()


def _decode(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        raise HTTPException(400, "Invalid cursor")


def _page(request: Request, key: str, items: list[dict], per_page: int, cursor: str | None) -> dict:
    after = _decode(cursor)
    items = sorted(items, key=lambda r: r["id"])
    start = next((i for i, r in enumerate(items) if r["id"] > after), len(items))
    if start > 0 and random.random() < _flaky()["overlap_rate"]:
        start -= 1   # records changed mid-pagination, so the last item of the previous page shows up again
    chunk = items[start:start + per_page]
    has_more = start + per_page < len(items)
    meta = {"has_more": has_more, "after_cursor": _encode(chunk[-1]["id"]) if chunk and has_more else None, "count": len(items)}
    links = {"next": None}
    if has_more:
        links["next"] = str(request.url.include_query_params(cursor=meta["after_cursor"]))
    return {key: chunk, "meta": meta, "links": links}


def _since(items: list[dict], field: str, since: str | None) -> list[dict]:
    return [r for r in items if r[field] >= since] if since else items


@app.get("/health")
def health() -> dict:
    meta = Path(SUPPORT_DIR).parent / "_meta.json"
    info = json.loads(meta.read_text()) if meta.exists() else {}
    return {"status": "ok", "data_as_of": info.get("as_of"), "generated_at": info.get("generated_at")}


@app.get("/api/v2/tickets", dependencies=[Depends(auth)])
def list_tickets(request: Request, per_page: int = Query(100, ge=1, le=MAX_PER_PAGE), cursor: str | None = None,
                 status: str | None = None, organization_id: int | None = None, updated_since: str | None = None):
    items = _since(_load("tickets"), "updated_at", updated_since)
    if status:
        items = [t for t in items if t["status"] == status]
    if organization_id is not None:
        items = [t for t in items if t["organization_id"] == organization_id]
    return _page(request, "tickets", items, per_page, cursor)


@app.get("/api/v2/tickets/search", dependencies=[Depends(auth)])
def search_tickets(request: Request, query: str, per_page: int = Query(25, ge=1, le=MAX_PER_PAGE), cursor: str | None = None):
    q = query.lower()
    hits = [t for t in _load("tickets") if q in t["subject"].lower() or q in t["description"].lower() or q in t["tags"]]
    return _page(request, "results", hits, per_page, cursor)


@app.get("/api/v2/tickets/{ticket_id}", dependencies=[Depends(auth)])
def get_ticket(ticket_id: int):
    for t in _load("tickets"):
        if t["id"] == ticket_id:
            return {"ticket": t}
    raise HTTPException(404, "RecordNotFound")


@app.get("/api/v2/tickets/{ticket_id}/comments", dependencies=[Depends(auth)])
def ticket_comments(request: Request, ticket_id: int, per_page: int = Query(100, ge=1, le=MAX_PER_PAGE), cursor: str | None = None):
    return _page(request, "comments", [c for c in _load("comments") if c["ticket_id"] == ticket_id], per_page, cursor)


@app.get("/api/v2/comments", dependencies=[Depends(auth)])
def all_comments(request: Request, per_page: int = Query(100, ge=1, le=MAX_PER_PAGE), cursor: str | None = None,
                 created_since: str | None = None):
    """Bulk export (not in the real Zendesk API, but typical of an ETL-friendly endpoint)."""
    return _page(request, "comments", _since(_load("comments"), "created_at", created_since), per_page, cursor)


@app.get("/api/v2/users", dependencies=[Depends(auth)])
def list_users(request: Request, per_page: int = Query(100, ge=1, le=MAX_PER_PAGE), cursor: str | None = None,
               role: str | None = None, updated_since: str | None = None):
    items = _since(_load("users"), "updated_at", updated_since)
    if role:
        items = [u for u in items if u["role"] == role]
    return _page(request, "users", items, per_page, cursor)


@app.get("/api/v2/organizations", dependencies=[Depends(auth)])
def list_organizations(request: Request, per_page: int = Query(100, ge=1, le=MAX_PER_PAGE), cursor: str | None = None,
                       updated_since: str | None = None):
    return _page(request, "organizations", _since(_load("organizations"), "updated_at", updated_since), per_page, cursor)


@app.get("/api/v2/groups", dependencies=[Depends(auth)])
def list_groups(request: Request, per_page: int = Query(100, ge=1, le=MAX_PER_PAGE), cursor: str | None = None):
    return _page(request, "groups", _load("groups"), per_page, cursor)


@app.get("/api/v2/ticket_fields", dependencies=[Depends(auth)])
def list_ticket_fields(request: Request, per_page: int = Query(100, ge=1, le=MAX_PER_PAGE), cursor: str | None = None):
    return _page(request, "ticket_fields", _load("ticket_fields"), per_page, cursor)
