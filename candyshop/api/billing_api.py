"""Billing exports, hosted as downloadable Parquet files (like a nightly export bucket).

    GET /api/v1/billing/exports                    -> list of files with rows, size, etag, last_modified
    GET /api/v1/billing/exports/invoices.parquet   -> the file; honours If-None-Match (304)
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse

from ..config import BILLING_DIR
from .support_api import auth

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


def _etag(path: Path) -> str:
    st = path.stat()
    return '"' + hashlib.md5(f"{path.name}:{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest() + '"'


def _lastmod(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


@router.get("/exports", dependencies=[Depends(auth)])
def list_exports():
    files = sorted(Path(BILLING_DIR).glob("*.parquet"))
    if not files:
        raise HTTPException(503, "billing exports not generated yet - run `candy init`")
    return {"exports": [
        {"name": f.name, "rows": pq.ParquetFile(f).metadata.num_rows, "bytes": f.stat().st_size, "etag": _etag(f),
         "last_modified": _lastmod(f), "url": f"/api/v1/billing/exports/{f.name}"} for f in files]}


@router.get("/exports/{name}", dependencies=[Depends(auth)])
def download(name: str, request: Request):
    if not re.fullmatch(r"[a-z_]+\.parquet", name):
        raise HTTPException(400, "bad file name")
    path = Path(BILLING_DIR) / name
    if not path.exists():
        raise HTTPException(404, "no such export")
    etag = _etag(path)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return FileResponse(path, media_type="application/vnd.apache.parquet", filename=name,
                        headers={"ETag": etag, "Last-Modified": _lastmod(path)})
