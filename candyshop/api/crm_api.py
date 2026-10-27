"""The CRM export, as a download link (a real CRM would email or expose an export file)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse

from ..config import CRM_DIR
from .support_api import auth

router = APIRouter(prefix="/api/v1/crm", tags=["crm"])
NAME = "crm_contacts_export.csv"


@router.get("/export", dependencies=[Depends(auth)])
def export(request: Request):
    path = Path(CRM_DIR) / NAME
    if not path.exists():
        raise HTTPException(503, "CRM export not generated yet - run `candy init`")
    st = path.stat()
    etag = '"' + hashlib.md5(f"{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest() + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return FileResponse(path, media_type="text/csv", filename=NAME, headers={
        "ETag": etag, "Last-Modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")})
