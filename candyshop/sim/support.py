"""Support desk (Zendesk-style): organizations, end-users, agents, tickets and comments.

Tickets are not random noise. They are triggered by what happens elsewhere: onboarding friction,
failed payments, cancellation intent, platform incidents, and pre-sales questions from prospects.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from .. import vocab as V
from .world import World, handler

TICKET_BASE = 0.0105       # tickets per active account-day (before scaling)
PRESALES_RATE = 0.0010
DOW_SUPPORT = [1.2, 1.2, 1.15, 1.1, 0.95, 0.25, 0.2]
CUSTOM_FIELD_ACCOUNT, CUSTOM_FIELD_AREA, CUSTOM_FIELD_PLAN = 360001, 360002, 360003


def seed_agent(w: World, idx: int, name: str, group: str) -> None:
    first = name.split()[0].lower()
    w.add("sup_users", dict(
        id=idx, name=name, email=f"{first}@sweetreach.example", role="agent" if group != "tier2" else "admin",
        organization_id=None, phone=None, time_zone="America/Chicago", created_at=datetime(2025, 3, 1), updated_at=datetime(2025, 3, 1),
        user_fields={"group": group}, active=True, _kind="agent"))


def _agents(w: World, group: str) -> list[dict]:
    return [u for u in w.t["sup_users"].values() if u["_kind"] == "agent" and u["user_fields"]["group"] == group]


def _org_for(w: World, acct: dict, ts: datetime) -> dict:
    orgs = w.index["acct_org"]
    if acct["account_id"] in orgs:
        return w.t["sup_orgs"][orgs[acct["account_id"]]]
    shop = w.shops[acct["_shop_id"]]
    name = shop["name"]
    r = w.rng.random()
    if r < 0.3:
        name = shop["legal_name"]
    elif r < 0.4:
        name = name.replace("The ", "")
    org = w.add("sup_orgs", dict(
        id=w.nid("org", 8001), name=name, domain_names=[shop["domain"]] if shop["domain"] and w.chance(0.8) else [],
        created_at=ts, updated_at=ts,
        organization_fields={"app_account_id": str(acct["account_id"]) if w.chance(0.85) else None,
                             "plan": acct["plan_id"], "state": acct["state"], "city": acct["city"]},
        _account_id=acct["account_id"]))
    orgs[acct["account_id"]] = org["id"]
    return org


def _user_for(w: World, name: str, email: str, org_id: int | None, ts: datetime, app_user_id: int | None) -> dict:
    by_email = w.index["sup_user_by_email"]
    key = email.lower()
    if key in by_email:
        return w.t["sup_users"][by_email[key]]
    u = w.add("sup_users", dict(
        id=w.nid("supuser", 61001), name=name, email=email, role="end-user", organization_id=org_id,
        phone=None, time_zone=None, created_at=ts, updated_at=ts, user_fields={"app_user_id": app_user_id},
        active=True, _kind="requester"))
    by_email[key] = u["id"]
    return u


def _fill(w: World, text: str, shop: dict | None, acct: dict | None, extra: dict | None = None) -> str:
    vals = dict(
        city=shop["city"] if shop else w.pick(V.CITIES)[0],
        lead_type=w.pick(list(V.LEAD_TYPES)).replace("_", " ").replace("pta", "PTA").replace("nonprofit", "nonprofit"),
        pos=(shop["pos"] if shop and shop["pos"] != "none" else w.pick(["Square", "Shopify", "Clover"])).title(),
        campaign=w.pick(["Halloween Bulk Bag Specials", "Valentine's Gift Box Preorders", "Back to School Fundraiser Packs",
                         "Weekend Sweet Deals"]),
        n=w.pick([25, 40, 120, 250, 500, 800]), month=w.pick(["August", "September", "October", "March", "May"]),
        plan=(acct["plan_id"] if acct else "Growth").title())
    if extra:
        vals.update(extra)
    return text.format(**vals)


# ---------------------------------------------------------------------------- ticket creation
def _create_ticket(w: World, ts: datetime, *, area: str, requester: dict, org: dict | None, acct: dict | None,
                   shop: dict | None, reason: str | None = None, subject: str | None = None,
                   description: str | None = None, priority: str | None = None, tags: list[str] | None = None,
                   incident: str | None = None) -> dict:
    if subject is None:
        subj, desc = w.pick(V.TICKET_TEMPLATES[area])
        subject, description = _fill(w, subj, shop, acct), _fill(w, desc, shop, acct)
    if reason == "payment_failed":
        subject, description = "Card declined but I updated it", (
            "I got a payment failed email for SweetReach. Our card is current - can you retry the charge?")
    elif reason == "cancellation":
        subject = w.pick(["How do I cancel my subscription?", "Please cancel at end of billing period",
                          "Thinking of pausing SweetReach"])
        description = w.pick([
            "Business has slowed and we need to cut costs. What happens to our leads if we cancel?",
            "We're not getting enough leads to justify the plan. Please explain how to cancel.",
            "We are closing the shop. Please stop billing us after this period."])
    priority = priority or w.pick(["low", "normal", "high", "urgent"], [0.25, 0.5, 0.2, 0.05])
    if area == "billing" and reason == "payment_failed":
        priority = "high"
    group = {"billing": "billing", "integrations": "tier2", "campaigns": "tier2"}.get(area, "tier1")
    if reason == "cancellation":
        group = "billing"
    if area == "presales":
        group = "tier1"
    agent = w.pick(_agents(w, group))
    ttype = {"billing": "question", "onboarding": "question", "reports": "question", "presales": "question"}.get(
        area, w.pick(["incident", "problem", "question"], [0.35, 0.3, 0.35]))
    if incident:
        ttype = "incident"
    channel = w.pick(["email", "web", "chat", "phone"], [0.5, 0.25, 0.2, 0.05])
    tid = w.nid("ticket", 30001)
    all_tags = [area] + (tags or []) + ([f"incident-{incident}"] if incident else []) + ([reason] if reason else [])
    plan = acct["plan_id"] if acct else None
    ticket = w.add("sup_tickets", dict(
        id=tid, subject=subject, description=description, status="new", priority=priority, type=ttype, via_channel=channel,
        tags=all_tags, requester_id=requester["id"], submitter_id=requester["id"], assignee_id=agent["id"],
        organization_id=org["id"] if org else None, group=group, created_at=ts, updated_at=ts, solved_at=None,
        satisfaction_rating=None, product_area=area,
        custom_fields=[{"id": CUSTOM_FIELD_ACCOUNT, "value": (org["organization_fields"]["app_account_id"] if org and w.chance(0.9) else None)},
                       {"id": CUSTOM_FIELD_AREA, "value": area}, {"id": CUSTOM_FIELD_PLAN, "value": plan}],
        _account_id=acct["account_id"] if acct else None))
    _add_comment(w, tid, requester["id"], True, description, ts, channel)
    _plan_timeline(w, ticket, ts, priority, area, reason, requester["name"].split()[0])
    return ticket


def _add_comment(w: World, tid: int, author_id: int, public: bool, body: str, ts: datetime, via: str) -> None:
    w.add("sup_comments", dict(id=w.nid("comment", 700001), ticket_id=tid, author_id=author_id, public=public, body=body,
                               created_at=ts, via_channel=via))


def _plan_timeline(w: World, ticket: dict, ts: datetime, priority: str, area: str, reason: str | None, first_name: str) -> None:
    tid = ticket["id"]
    fr_median = {"urgent": 25, "high": 55, "normal": 110, "low": 240}[priority]      # minutes
    res_median = {"billing": 7, "onboarding": 14, "reports": 20, "orders": 22, "campaigns": 30, "lead_finder": 34,
                  "integrations": 44, "presales": 10}.get(area, 24)                    # hours
    t = ts + timedelta(minutes=w.lognorm(fr_median, 0.7))
    needs_info = w.chance(0.45)
    w.schedule(t, "ticket_step", ticket_id=tid, author="agent", status="pending" if needs_info else "open", step="reply", name=first_name)
    if w.chance(0.03):   # never resolved - customer went quiet
        return
    if needs_info:
        t = t + timedelta(hours=w.lognorm(5, 0.9))
        w.schedule(t, "ticket_step", ticket_id=tid, author="requester", status="open", step="followup", name=first_name)
        t = t + timedelta(hours=w.lognorm(2.5, 0.7))
        w.schedule(t, "ticket_step", ticket_id=tid, author="agent", status="open", step="reply", name=first_name)
    solve_at = max(t + timedelta(minutes=20), ts + timedelta(hours=w.lognorm(res_median, 0.8)))
    w.schedule(solve_at, "ticket_step", ticket_id=tid, author="agent", status="solved", step="solved", name=first_name)
    hours = (solve_at - ts).total_seconds() / 3600
    if w.chance(0.35):
        w.schedule(solve_at + timedelta(hours=w.rng.uniform(0.2, 6)), "ticket_step", ticket_id=tid, author="requester",
                   status=None, step="thanks", name=first_name)
    if w.chance(0.66):
        p_good = max(0.25, min(0.95, 0.93 - 0.01 * hours))
        if reason == "cancellation":
            p_good *= 0.6
        w.schedule(solve_at + timedelta(days=w.rng.uniform(0.5, 3)), "ticket_csat", ticket_id=tid, good=w.chance(p_good))
    w.schedule(solve_at + timedelta(days=7), "ticket_close", ticket_id=tid)


@handler("ticket_step")
def _h_step(w: World, due: datetime, ticket_id: int, author: str, status: str | None, step: str, name: str) -> None:
    t = w.t["sup_tickets"][ticket_id]
    if t["status"] in ("closed",):
        return
    if author == "agent":
        author_id = t["assignee_id"]
        agent_first = w.t["sup_users"][author_id]["name"].split()[0]
        body = w.pick(V.AGENT_SOLVED if step == "solved" else V.AGENT_REPLIES).format(name=name)
        body += f"\n\n- {agent_first}, SweetReach Support"
        public = True
    else:
        author_id = t["requester_id"]
        body = w.pick(V.REQUESTER_THANKS if step == "thanks" else V.REQUESTER_FOLLOWUPS)
        public = True
    _add_comment(w, ticket_id, author_id, public, body, due, "email" if t["via_channel"] != "chat" else "chat")
    if status:
        t["status"] = status
    if status == "solved":
        t["solved_at"] = due
    t["updated_at"] = due


@handler("ticket_csat")
def _h_csat(w: World, due: datetime, ticket_id: int, good: bool) -> None:
    t = w.t["sup_tickets"][ticket_id]
    t["satisfaction_rating"] = {"score": "good" if good else "bad",
                                "comment": w.pick(V.CSAT_COMMENTS_GOOD if good else V.CSAT_COMMENTS_BAD) or None}
    t["updated_at"] = due


@handler("ticket_close")
def _h_close(w: World, due: datetime, ticket_id: int) -> None:
    t = w.t["sup_tickets"][ticket_id]
    if t["status"] == "solved":
        t["status"] = "closed"
        t["updated_at"] = due


# ---------------------------------------------------------------------------- triggers
def _requester_for_account(w: World, acct: dict, ts: datetime) -> tuple[dict, dict]:
    org = _org_for(w, acct, ts)
    uids = w.index["acct_users"][acct["account_id"]]
    weights = [3 if w.t["app_users"][u]["role"] == "owner" else 1 for u in uids]
    au = w.t["app_users"][w.pick(uids, weights)]
    email = au["email"]
    if w.chance(0.10):  # writes in from a personal address that the app has never seen
        first = au["full_name"].split()[0].lower()
        email = f"{first}{w.rng.randint(10, 99)}@{w.pick(V.FREE_MAIL[:3])}"
    return _user_for(w, au["full_name"], email, org["id"], ts, au["user_id"]), org


def create_account_ticket(w: World, ts: datetime, acct: dict, *, area: str, reason: str | None = None,
                          incident: str | None = None, subject: str | None = None, description: str | None = None,
                          priority: str | None = None) -> dict:
    shop = w.shops[acct["_shop_id"]]
    requester, org = _requester_for_account(w, acct, ts)
    return _create_ticket(w, ts, area=area, requester=requester, org=org, acct=acct, shop=shop, reason=reason,
                          incident=incident, subject=subject, description=description, priority=priority)


@handler("ticket_trigger")
def _h_trigger(w: World, due: datetime, account_id: int, area: str, reason: str) -> None:
    acct = w.t["app_accounts"][account_id]
    if acct["status"] != "churned":
        create_account_ticket(w, due, acct, area=area, reason=reason)


def _presales(w: World, shop: dict, ts: datetime) -> None:
    contacts = [w.t["crm_contacts"][r] for r in shop["contact_ids"] if not w.t["crm_contacts"][r]["_dup"]]
    c = contacts[0]
    u = _user_for(w, f"{c['first_name']} {c['last_name']}", c["email"].lower(), None, ts, None)
    _create_ticket(w, ts, area="presales", requester=u, org=None, acct=None, shop=shop, priority="normal")


def daily(w: World, d: date) -> None:
    dow = DOW_SUPPORT[d.weekday()]
    # --- incidents: known dates plus the occasional new one as the world rolls forward
    if d not in w.incidents and d > date(2026, 10, 25) and w.chance(1 / 75):
        area = w.pick(["campaigns", "lead_finder"])
        w.incidents[d] = (area, w.pick(["Delayed report generation", "Webhook delivery failures", "Slow dashboard loads",
                                         "Intermittent login errors", "Scheduled sends delayed"]))
    inc_day = d if d in w.incidents else d - timedelta(days=1)
    incident = w.incidents.get(inc_day)
    inc_rate = 0.11 if d in w.incidents else 0.04
    for acct in w.t["app_accounts"].values():
        if acct["status"] in ("churned", "merged"):
            continue
        shop = w.shops[acct["_shop_id"]]
        age = (d - acct["created_at"].date()).days
        n_users = len(w.index["acct_users"][acct["account_id"]])
        lam = TICKET_BASE * math.sqrt(n_users) * dow * (1 + 1.6 * max(0, 1 - age / 30)) * (1.9 if shop["decay"] < 1 else 1.0)
        for _ in range(w.poisson(lam)):
            weights = []
            for area, wt in V.AREA_WEIGHTS.items():
                if area == "onboarding":
                    wt *= 4 if age < 30 else 0.25
                weights.append(wt)
            area = w.pick(list(V.AREA_WEIGHTS), weights)
            create_account_ticket(w, w.moment(d, 7, 20), acct, area=area)
        if incident and w.chance(inc_rate):
            area, title = incident
            subj_t, desc_t = V.INCIDENT_TEMPLATES.get(area, V.INCIDENT_TEMPLATES["campaigns"])
            create_account_ticket(w, w.moment(d, 7, 20), acct, area=area, incident=inc_day.isoformat(),
                                  subject=subj_t.format(title=title), description=desc_t.format(title=title), priority="high")
    # --- pre-sales questions from prospects deep in the funnel
    for shop in w.shops.values():
        if shop["status"] == "prospect" and shop["stage"] in ("SQL", "Opportunity") and w.chance(PRESALES_RATE * dow):
            _presales(w, shop, w.moment(d, 8, 18))
