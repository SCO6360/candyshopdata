"""SweetReach's own marketing: campaigns, webinars, trade shows, web traffic and email nurture.

Two systems feed the exported JSON: a marketing-automation tool (ISO timestamps, identified by
email) and web analytics (epoch-millisecond timestamps, mostly anonymous). Anonymous visitors are
stitched to an email only when they submit a form.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .. import vocab as V
from .text import fill
from .world import World

ORIGIN_P = {"Trade Show": 0.85, "Webinar": 0.75}  # share of new CRM contacts that leave a visible marketing trail
ORIGIN_DEFAULT_P = 0.36
NURTURE_P = 0.16     # chance a contact gets a nurture email sequence when it reaches MQL
DEMO_P = 0.25
ANON_RATE = 0.10     # anonymous visits per day

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


# ---------------------------------------------------------------------------- calendar
def _second_tuesday(year: int, month: int) -> date:
    d = date(year, month, 1)
    first_tue = d + timedelta(days=(1 - d.weekday()) % 7)
    return first_tue + timedelta(days=7)


def ensure_campaigns(w: World, year: int) -> None:
    cal = w.index["calendar"]
    if year in cal:
        return
    cal[year] = True
    n = 0

    def add(name, ctype, channel, start, end, budget):
        nonlocal n
        n += 1
        cid = f"MC-{year}-{n:02d}"
        w.mkt_campaigns[cid] = dict(
            campaign_id=cid, name=name, type=ctype, channel=channel, start=start, end=end,
            utm_campaign=re.sub(r"[^a-z0-9]+", "_", name.lower().replace("&", "and")).strip("_"), budget_usd=budget)

    for m in range(1, 13):
        d = _second_tuesday(year, m)
        add(f"Candy Shop Growth Webinar - {MONTHS[m - 1]} {year}", "webinar", "webinar", d, d, 1500)
    add(f"Find Your Sweet-Tooth Crowd (Paid Social) {year}", "paid_social", "paid_social", date(year, 1, 1), date(year, 12, 31), 36000)
    add(f"Candy Shop Owners Outbound Sequence {year}", "outbound", "email", date(year, 1, 1), date(year, 12, 31), 9000)
    add(f"Valentine's Playbook {year}", "nurture", "email", date(year, 1, 5), date(year, 2, 8), 2000)
    add(f"Spring Sales Kickoff {year}", "nurture", "email", date(year, 3, 1), date(year, 4, 10), 2000)
    add(f"Back-to-School Fundraiser Guide {year}", "nurture", "email", date(year, 6, 1), date(year, 8, 15), 2500)
    add(f"Halloween Readiness Playbook {year}", "nurture", "email", date(year, 8, 10), date(year, 10, 20), 3000)
    add(f"Holiday Gift Box Guide {year}", "nurture", "email", date(year, 10, 1), date(year, 12, 5), 3000)
    add(f"Candy Makers Expo {year}", "trade_show", "event", date(year, 5, 12), date(year, 5, 14), 22000)
    add(f"Regional Confectioners Show {year}", "trade_show", "event", date(year, 9, 20), date(year, 9, 21), 9000)


def active(w: World, d: date, ctype: str | None = None) -> list[dict]:
    ensure_campaigns(w, d.year)
    return [c for c in w.mkt_campaigns.values()
            if c["start"] <= d <= c["end"] and (ctype is None or c["type"] == ctype)]


def _latest(w: World, d: date, ctype: str, within: int) -> dict | None:
    for yr in (d.year, d.year - 1):
        ensure_campaigns(w, yr)
    best = None
    for c in w.mkt_campaigns.values():
        if c["type"] == ctype and c["start"] <= d and (d - c["end"]).days <= within:
            if best is None or c["start"] > best["start"]:
                best = c
    return best


def days_since_show(w: World, d: date) -> int | None:
    c = _latest(w, d, "trade_show", 14)
    return (d - c["end"]).days if c else None


def days_since_webinar(w: World, d: date) -> int | None:
    c = _latest(w, d, "webinar", 7)
    return (d - c["start"]).days if c else None


def campaign_for_source(w: World, source: str, d: date) -> dict | None:
    if source == "Trade Show":
        return _latest(w, d, "trade_show", 14)
    if source == "Webinar":
        return _latest(w, d, "webinar", 7)
    if source == "Paid Social":
        c = active(w, d, "paid_social")
        return c[0] if c else None
    if source == "Cold Outreach":
        c = active(w, d, "outbound")
        return c[0] if c else None
    if source == "Inbound Web":
        c = active(w, d, "nurture")
        return w.pick(c) if c else None
    return None


# ---------------------------------------------------------------------------- events
def emit(w: World, etype: str, ts: datetime, *, email: str | None = None, anon: str | None = None,
         contact_id: int | None = None, campaign: dict | None = None, system: str = "marketing_automation",
         props: dict | None = None, page_url: str | None = None, shop_id: str | None = None, bot: bool = False) -> dict:
    utm = None
    if campaign:
        utm = dict(source={"paid_social": "facebook", "outbound": "outreach", "webinar": "livestorm",
                           "trade_show": "expo", "nurture": "newsletter"}.get(campaign["type"], "web"),
                   medium={"paid_social": "paid_social", "outbound": "email", "webinar": "webinar",
                           "trade_show": "event", "nurture": "email"}.get(campaign["type"], "organic"),
                   campaign=campaign["utm_campaign"])
    row = dict(
        event_id=w.uuid(), event_type=etype, occurred_at=ts, system=system, anonymous_id=anon,
        email=email, crm_contact_id=contact_id, campaign_id=campaign["campaign_id"] if campaign else None,
        utm=utm, properties=props or {}, page_url=page_url,
        device=(dict(type=w.pick(["desktop", "mobile", "tablet"], [0.55, 0.4, 0.05]),
                     os=w.pick(["Windows", "macOS", "iOS", "Android"], [0.32, 0.28, 0.25, 0.15]))
                if system == "web_analytics" else None),
        _shop_id=shop_id, _bot=bot,
    )
    w.add("mkt_events", row)
    return row


def on_contact_created(w: World, shop: dict, c: dict, ts: datetime, campaign: dict | None) -> None:
    """Leave a marketing trail that precedes the CRM record (sync lag), keyed by email/anonymous id."""
    src, email, rid = c["lead_source"], c["email"].lower(), c["record_id"]
    if not w.chance(ORIGIN_P.get(src, ORIGIN_DEFAULT_P)):
        return
    anon, sid = shop["anon_id"], shop["shop_id"]
    back = lambda lo, hi: ts - timedelta(days=w.rng.uniform(lo, hi))  # noqa: E731
    if src == "Webinar" and campaign:
        emit(w, "webinar_registered", back(2, 5), email=email, contact_id=rid, campaign=campaign, shop_id=sid,
             props={"webinar": campaign["name"]})
        if w.chance(0.65):
            emit(w, "webinar_attended", back(0.2, 1.5), email=email, contact_id=rid, campaign=campaign, shop_id=sid,
                 props={"minutes_watched": int(w.rng.uniform(12, 58)),
                                                                                         **({"question": w.pick(V.WEBINAR_QUESTIONS)} if w.chance(0.3) else {})})
    elif src == "Trade Show" and campaign:
        emit(w, "trade_show_scan", back(0.1, 2.5), email=email, contact_id=rid, campaign=campaign, shop_id=sid,
             props={"event": campaign["name"], "booth": w.pick(["A114", "B207", "C031"]),
                    "interest": w.pick(["fundraisers", "weddings", "corporate gifts", "holiday sales"]),
                    "scanned_by": w.pick(V.SALES_REPS)})
    elif src in ("Inbound Web", "Paid Social", "Referral"):
        organic = src == "Inbound Web"
        if src == "Paid Social":
            emit(w, "ad_click", back(0.1, 2), anon=anon, system="web_analytics", campaign=campaign, shop_id=sid,
                 props={"creative": w.pick(V.AD_CREATIVES), "platform": w.pick(["facebook", "instagram"])},
                 page_url="/lp/find-your-sweet-tooth-crowd")
        for _ in range(w.rng.randint(1, 3 if organic else 2)):
            emit(w, "page_view", back(0.05, 3), anon=anon, system="web_analytics", campaign=campaign, shop_id=sid,
                 page_url=w.pick(V.WEB_PAGES))
        props = {"form": "request_demo" if w.chance(0.6) else "newsletter", "company": shop["name"], "state": shop["state"]}
        if w.chance(0.55):
            props["message"] = fill(w.pick(V.FORM_MESSAGES), city=shop["city"], pos=shop["pos"].title() if shop["pos"] != "none" else "our register")
        if src == "Referral":
            props["referral_code"] = f"REF-{w.rng.randint(1000, 9999)}"
        emit(w, "form_submit", back(0, 0.5), email=email, anon=anon, contact_id=rid, campaign=campaign, shop_id=sid,
             props=props)
    elif src == "Cold Outreach" and campaign:
        emit(w, "email_sent", back(1, 6), email=email, contact_id=rid, campaign=campaign, shop_id=sid,
             props={"step": 1, "subject": "Fill your calendar with school & wedding candy orders"})
        if w.chance(0.5):
            emit(w, "email_open", back(0.8, 5.5), email=email, contact_id=rid, campaign=campaign, shop_id=sid, props={"step": 1})
            if w.chance(0.35):
                emit(w, "email_click", back(0.5, 5), email=email, contact_id=rid, campaign=campaign, shop_id=sid,
                     props={"step": 1, "link": "/demo"})
    elif src == "Partner - Distributor":
        emit(w, "partner_lead_import", back(0.5, 4), email=email, contact_id=rid, shop_id=sid,
             props={"partner": w.pick(["Confectionery Wholesale Group", "Sweet Supply Co-op", "Midwest Candy Distributors"])})


def on_stage(w: World, shop: dict, stage: str, ts: datetime) -> None:
    contact = next((w.t["crm_contacts"][r] for r in shop["contact_ids"] if not w.t["crm_contacts"][r]["_dup"]), None)
    if contact is None:
        return
    email, rid = contact["email"].lower(), contact["record_id"]
    if stage == "MQL" and w.chance(NURTURE_P):
        camp = w.pick(active(w, ts.date(), "nurture") or [None])
        if camp:
            emit(w, "email_sent", ts + timedelta(hours=2), email=email, contact_id=rid, campaign=camp, shop_id=shop["shop_id"],
                 props={"subject": camp["name"]})
            if w.chance(0.55):
                emit(w, "email_open", ts + timedelta(hours=w.rng.uniform(3, 30)), email=email, contact_id=rid, campaign=camp,
                     shop_id=shop["shop_id"])
                if w.chance(0.3):
                    asset = w.pick(V.CONTENT_ASSETS)
                    emit(w, "content_download", ts + timedelta(hours=w.rng.uniform(4, 40)), email=email, contact_id=rid,
                         campaign=camp, shop_id=shop["shop_id"], props={"asset": asset})
    if stage == "SQL" and w.chance(DEMO_P):
        emit(w, "demo_requested", ts - timedelta(hours=w.rng.uniform(1, 40)), email=email, contact_id=rid,
             shop_id=shop["shop_id"], props={"preferred_time": w.pick(["morning", "afternoon"]),
                                              "employees": shop["employees"]})


def on_signup(w: World, shop: dict, acct: dict, ts: datetime) -> None:
    """Product -> marketing automation: a trial_started event ties the email to the app account id."""
    if w.chance(0.55):
        emit(w, "trial_started", ts + timedelta(minutes=w.rng.uniform(1, 30)), email=shop["owner_email"].lower(),
             shop_id=shop["shop_id"],
             props={"app_account_id": acct["account_id"], "plan": acct["plan_id"], "signup_source": acct["signup_source"]})


def daily(w: World, d: date) -> None:
    ensure_campaigns(w, d.year)
    if w.mess(0.004):   # a crawler hammers the site: dozens of page views from one "visitor" in a couple of minutes
        bot, t0 = w.uuid(), w.moment(d, 0, 23)
        for _ in range(w.rng.randint(8, 30)):
            emit(w, "page_view", t0 + timedelta(seconds=w.rng.uniform(0, 120)), anon=bot, system="web_analytics",
                 page_url=w.pick(V.WEB_PAGES), props={"user_agent": "HeadlessChrome/118.0 (compatible; crawler)"}, bot=True)
    from .crm import DOW_B2B, growth
    for _ in range(w.poisson(ANON_RATE * growth(d) * DOW_B2B[d.weekday()])):
        ts = w.moment(d, 6, 23)
        if w.chance(0.3):
            camp = active(w, d, "paid_social")
            emit(w, "ad_click", ts, anon=w.uuid(), system="web_analytics", campaign=camp[0] if camp else None,
                 props={"creative": w.pick(V.AD_CREATIVES), "platform": w.pick(["facebook", "instagram"])},
                 page_url="/lp/find-your-sweet-tooth-crowd")
        else:
            emit(w, "page_view", ts, anon=w.uuid(), system="web_analytics", page_url=w.pick(V.WEB_PAGES))
