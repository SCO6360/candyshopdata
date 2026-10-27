"""Source 5 - the support desk, exposed as a REST API (see candyshop/api/support_api.py).

This module writes the API-shaped JSON documents the server reads: tickets, comments, users,
organizations and groups, modelled on a Zendesk-style v2 API. The link to the app is a custom
field / organization field holding the app account id (as a *string*, and not always present).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..sim.world import World

GROUP_IDS = {"tier1": 1001, "tier2": 1002, "billing": 1003}


def _iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _rating(t: dict) -> dict:
    if t["satisfaction_rating"]:
        return {k: v for k, v in t["satisfaction_rating"].items() if v is not None}
    if t["status"] in ("solved", "closed") and t["id"] % 7 == 0:
        return {"score": "offered"}
    return {"score": "unoffered"}


def _ticket(w: World, t: dict, first_reply: dict[int, datetime]) -> dict:
    fr = first_reply.get(t["id"])
    return {
        "id": t["id"], "url": f"/api/v2/tickets/{t['id']}", "subject": t["subject"], "description": t["description"],
        "status": t["status"], "priority": t["priority"], "type": t["type"], "via": {"channel": t["via_channel"]},
        "tags": t["tags"], "requester_id": t["requester_id"], "submitter_id": t["submitter_id"], "assignee_id": t["assignee_id"],
        "organization_id": t["organization_id"], "group_id": GROUP_IDS[t["group"]],
        "created_at": _iso(t["created_at"]), "updated_at": _iso(t["updated_at"]),
        "satisfaction_rating": _rating(t), "custom_fields": t["custom_fields"],
        "metric_set": {
            "solved_at": _iso(t["solved_at"]),
            "first_reply_time_minutes": round((fr - t["created_at"]).total_seconds() / 60) if fr else None,
            "full_resolution_time_minutes": round((t["solved_at"] - t["created_at"]).total_seconds() / 60) if t["solved_at"] else None,
        },
    }


def write(w: World, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    agent_ids = {u["id"] for u in w.t["sup_users"].values() if u["_kind"] == "agent"}
    first_reply: dict[int, datetime] = {}
    for c in sorted(w.t["sup_comments"].values(), key=lambda c: c["created_at"]):
        if c["author_id"] in agent_ids and c["ticket_id"] not in first_reply:
            first_reply[c["ticket_id"]] = c["created_at"]

    tickets = [_ticket(w, t, first_reply) for t in sorted(w.t["sup_tickets"].values(), key=lambda t: t["id"])]
    comments = [{"id": c["id"], "ticket_id": c["ticket_id"], "author_id": c["author_id"], "public": c["public"], "body": c["body"],
                 "created_at": _iso(c["created_at"]), "via": {"channel": c["via_channel"]}}
                for c in sorted(w.t["sup_comments"].values(), key=lambda c: c["id"])]
    users = [{"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "organization_id": u["organization_id"],
              "time_zone": u["time_zone"], "active": u["active"], "created_at": _iso(u["created_at"]),
              "updated_at": _iso(u["updated_at"]), "user_fields": u["user_fields"]}
             for u in sorted(w.t["sup_users"].values(), key=lambda u: u["id"])]
    orgs = [{"id": o["id"], "name": o["name"], "domain_names": o["domain_names"], "created_at": _iso(o["created_at"]),
             "updated_at": _iso(o["updated_at"]), "organization_fields": o["organization_fields"]}
            for o in sorted(w.t["sup_orgs"].values(), key=lambda o: o["id"])]
    groups = [{"id": gid, "name": name} for name, gid in GROUP_IDS.items()]
    custom_fields = [{"id": 360001, "title": "SweetReach Account ID", "type": "text"},
                     {"id": 360002, "title": "Product Area", "type": "dropdown"},
                     {"id": 360003, "title": "Plan", "type": "dropdown"}]
    docs = {"tickets": tickets, "comments": comments, "users": users, "organizations": orgs, "groups": groups,
            "ticket_fields": custom_fields}
    # the mock API reads this to decide how unreliable to be (0 = perfectly healthy)
    rate = (0.0, 0.01, 0.03, 0.08)[w.messiness]
    with open(out_dir / "_api_config.json", "w") as fh:
        json.dump({"error_rate": rate, "overlap_rate": rate, "messiness": w.messiness}, fh)
    for name, doc in docs.items():
        with open(out_dir / f"{name}.json", "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)
    return {k: len(v) for k, v in docs.items()}
