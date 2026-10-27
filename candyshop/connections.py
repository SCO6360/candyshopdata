"""Everything the next step needs to pick up the data: where each source is and how to authenticate."""
from __future__ import annotations

import json
from urllib.parse import urlsplit, urlunsplit

from . import config as C

READER_USER = READER_PASSWORD = "candy_reader"


def reader_url(admin_url: str = C.DEFAULT_DB_URL) -> str:
    p = urlsplit(admin_url)
    host = p.hostname or "localhost"
    netloc = f"{READER_USER}:{READER_PASSWORD}@{host}" + (f":{p.port}" if p.port else "")
    return urlunsplit((p.scheme, netloc, p.path, "", ""))


def build() -> dict:
    api = C.DEFAULT_SUPPORT_URL.rstrip("/")
    auth = {"header": "Authorization", "value": f"Bearer {C.SUPPORT_API_TOKEN}"}
    return {
        "note": "Demo credentials for fake data. Re-run `candy connections` any time; `candy grow` keeps all of these current.",
        "postgres": {"read_only_url": reader_url(), "admin_url": C.DEFAULT_DB_URL, "schema": "app",
                     "tables": ["accounts", "users", "leads", "campaigns", "orders", "order_items", "products", "plans",
                                "exit_surveys", "nps_responses"]},
        "support_api": {"base_url": f"{api}/api/v2", "auth": auth, "paging": "cursor: meta.after_cursor -> ?cursor=",
                        "incremental": "?updated_since=<ISO>", "endpoints": ["/tickets", "/comments", "/users", "/organizations", "/groups"]},
        "marketing_api": {"base_url": f"{api}/api/v1/marketing", "auth": auth, "paging": "next_page_token -> ?page_token=",
                          "incremental": "?since=<ISO>", "endpoints": ["/events", "/campaigns", "/meta"]},
        "billing_exports": {"base_url": f"{api}/api/v1/billing/exports", "auth": auth,
                            "format": "Parquet (use If-None-Match with the ETag to skip unchanged files)",
                            "files": ["customers.parquet", "subscriptions.parquet", "invoices.parquet", "payments.parquet"]},
        "crm_export": {"download_url": f"{api}/api/v1/crm/export", "auth": auth, "format": "CSV",
                       "local_file": str(C.CRM_DIR / "crm_contacts_export.csv")},
        "docs": f"{api}/docs",
        "freshness": f"{api}/health   (data_as_of must equal the date shown by `candy status`)",
    }


def write(path=None) -> dict:
    info = build()
    path = path or C.DATA_DIR / "_connections.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info, indent=2))
    return info


def render(info: dict) -> str:
    pg, s, m, b, c = info["postgres"], info["support_api"], info["marketing_api"], info["billing_exports"], info["crm_export"]
    return f"""How to pick up each source
---------------------------------------------------------------------------------
PostgreSQL (read-only)  {pg['read_only_url']}
  schema {pg['schema']}: {', '.join(pg['tables'])}
Support REST API        {s['base_url']}    header {s['auth']['header']}: {s['auth']['value']}
  {', '.join(s['endpoints'])}   paging: {s['paging']}   incremental: {s['incremental']}
Marketing REST API      {m['base_url']}    (same auth header)
  {', '.join(m['endpoints'])}   paging: {m['paging']}   incremental: {m['incremental']}
Billing Parquet         {b['base_url']}/<name>.parquet    (same auth header)
  {', '.join(b['files'])}
CRM CSV                 {c['download_url']}    (same auth header)   or the file {c['local_file']}
Interactive docs        {info['docs']}
Freshness check         {info['freshness']}
"""
