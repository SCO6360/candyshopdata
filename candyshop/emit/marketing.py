"""Source 3 - JSON export from the marketing stack.

Two systems are merged in one file, with the different conventions that implies:

* ``marketing_automation`` (email, webinars, forms, trade-show scans): ISO-8601 ``occurred_at``, a
  nested ``contact`` block identified by email, snake_case.
* ``web_analytics`` (page views, ad clicks): epoch-millisecond ``ts``, ``anonymousId``, camelCase,
  mostly anonymous until the visitor submits a form.

``properties`` differs per event type, so the structure is genuinely semi-structured.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..sim.world import World


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and v != {}}


DRIFT = datetime(2026, 3, 1)   # marketing-automation vendor v2 renamed fields from this date on


def _h(event_id: str) -> int:
    return int(hashlib.md5(event_id.encode()).hexdigest()[:8], 16) % 1000


def _event(w: World, e: dict) -> dict:
    camp = w.mkt_campaigns.get(e["campaign_id"]) if e["campaign_id"] else None
    campaign = {"id": camp["campaign_id"], "name": camp["name"], "channel": camp["channel"]} if camp else None
    if e["system"] == "web_analytics":
        return _clean({
            "event_id": e["event_id"], "event_type": e["event_type"], "source_system": "web_analytics", "ts": _epoch_ms(e["occurred_at"]),
            "anonymousId": e["anonymous_id"],
            "context": _clean({"page": {"url": e["page_url"]} if e["page_url"] else None, "campaign": e["utm"], "device": e["device"]}),
            "campaign": campaign, "properties": e["properties"],
        })
    contact = _clean({"email": e["email"], "crm_record_id": e["crm_contact_id"], "anonymous_id": e["anonymous_id"]})
    if w.messiness > 0 and e["occurred_at"] >= DRIFT:      # v2 payload: same facts, different names
        utm = e["utm"] and {"src": e["utm"]["source"], "med": e["utm"]["medium"], "cmp": e["utm"]["campaign"]}
        return _clean({
            "event_id": e["event_id"], "event_type": e["event_type"], "source_system": "marketing_automation", "schema": 2,
            "occurred_at": _iso(e["occurred_at"]),
            "person": _clean({"email_address": e["email"], "crm_id": e["crm_contact_id"], "anonymous_id": e["anonymous_id"]}),
            "campaign": campaign, "attribution": utm, "properties": e["properties"],
        })
    return _clean({
        "event_id": e["event_id"], "event_type": e["event_type"], "source_system": "marketing_automation",
        "occurred_at": _iso(e["occurred_at"]), "contact": contact, "campaign": campaign, "utm": e["utm"], "properties": e["properties"],
    })


def write(w: World, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    events = sorted(w.t["mkt_events"].values(), key=lambda e: (e["occurred_at"], e["event_id"]))
    m = (0.0, 0.5, 1.0, 2.0)[w.messiness]
    campaigns = [
        {"campaign_id": c["campaign_id"], "name": c["name"], "type": c["type"], "channel": c["channel"],
         "start_date": c["start"].isoformat(), "end_date": c["end"].isoformat(), "utm_campaign": c["utm_campaign"],
         "budget_usd": c["budget_usd"]}
        for c in sorted(w.mkt_campaigns.values(), key=lambda c: (c["start"], c["campaign_id"]))
    ]
    doc = {
        "export_meta": {
            "source": "SweetReach Marketing Hub", "schema_version": "2.1", "as_of": w.clock.isoformat(),
            "event_count": len(events),
            "systems": {"marketing_automation": "ISO-8601 occurred_at, contact identified by email",
                        "web_analytics": "epoch-millisecond ts, anonymousId, camelCase"},
            "note": "Only identified contacts and sampled anonymous traffic are exported. Join to CRM on contact.email.",
        },
        "campaigns": campaigns,
        "events": [],
    }
    late = []
    for e in events:
        rec = _event(w, e)
        h = _h(e["event_id"])
        if h < 50 * m:                      # delivered late, out of order, at the end of the file
            late.append(rec)
            continue
        doc["events"].append(rec)
        if h >= 1000 - 30 * m:              # webhook delivered twice: identical event_id
            doc["events"].append(dict(rec))
        elif h >= 1000 - 50 * m:            # client retry: new event_id, a few seconds later
            retry = dict(rec, event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, e["event_id"])))
            if "occurred_at" in retry:
                retry["occurred_at"] = _iso(e["occurred_at"] + timedelta(seconds=1 + h % 60))
            else:
                retry["ts"] = rec["ts"] + (1 + h % 60) * 1000
            doc["events"].append(retry)
    doc["events"].extend(late)
    doc["export_meta"]["event_count"] = len(doc["events"])
    with open(out_dir / "marketing_events.json", "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return len(doc["events"])
