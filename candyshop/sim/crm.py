"""Candy shops, and the third-party CRM that sales uses to prospect them."""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta

from .. import vocab as V
from ..config import APP_LAUNCH, CRM_START
from .text import fill
from .world import World, handler

CRM_BASE_RATE = 1.95       # new prospects per (average) weekday-weighted day
SELF_SERVE_RATE = 0.115    # product-led signups per day after launch
DOW_B2B = [1.25, 1.25, 1.25, 1.25, 1.0, 0.25, 0.15]
FOCUS = ["school fundraisers", "wedding favors", "corporate gifting", "holiday gift boxes", "bulk orders",
         "party favors", "festival booths"]


def growth(d: date) -> float:
    t = (d - CRM_START).days
    return min(0.45 + 0.55 * t / 573, 1.6)


def slug(text: str) -> str:
    text = re.sub(r"^the\s+", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "", text.replace("'s", "s"))


# ---------------------------------------------------------------------------- shops
def make_shop(w: World, d: date, origin: str) -> dict:
    f = w.fake
    city, state, tz, zip3 = w.pick(V.CITIES, V.CITY_WEIGHTS)
    first, last = f.first_name(), f.last_name()
    parent = None
    pool = w.index["chain_pool"]
    if origin == "crm" and pool and w.mess(0.06):
        parent = w.shops[w.pick(list(pool))]
    if parent is not None:   # another location of an existing multi-store owner: same owner, domain, phone
        first, last = parent["owner_first"], parent["owner_last"]
        for _ in range(6):
            city, state, tz, zip3 = w.pick(V.CITIES, V.CITY_WEIGHTS)
            if city != parent["city"]:
                break
        name = f"{parent['brand']} - {city}"
        names = w.index["shop_names"]
        if (name, state) in names:
            name = f"{name} #{w.rng.randint(2, 9)}"
        names[(name, state)] = True
    else:
        name = new_shop_name(w, city, state, last)
    employees = int(min(60, max(1, w.lognorm(5, 0.7))))
    e = min(6.0, max(0.15, w.lognorm(1.0, 0.75) * (1 + employees / 40) / 1.15))
    domain = parent["domain"] if parent else None
    if parent is None and w.chance(0.86):
        base = slug(name)
        suffix = w.pick([".com", ".com", ".com", ".shop", ".net"])
        domain = base + suffix
        if domain in w.index["domains"]:
            domain = base + state.lower() + suffix
        w.index["domains"][domain] = True
    if parent is not None:
        email = parent["owner_email"]
    elif domain and w.chance(0.75):
        style = w.pick(["{f}.{l}", "{f}", "{f}{l}", "{fi}{l}"])
        email = style.format(f=first.lower(), l=last.lower(), fi=first[0].lower()) + "@" + domain
    else:
        email = f"{first.lower()}{last.lower()}{w.rng.randint(1, 99)}@{w.pick(V.FREE_MAIL[:4])}"
    email = re.sub(r"[^a-z0-9.@_+-]", "", email)

    sid = f"SHP-{w.nid('shop', 1):05d}"
    pro_p = min(0.28, employees / 70)
    plan_intent = w.pick(V.PLAN_ORDER, [max(0.15, 0.62 - employees / 40), 0.32, pro_p])
    shop = dict(
        shop_id=sid, name=name, legal_name=f"{name} {w.pick(V.LEGAL_SUFFIXES)}".strip(), domain=domain,
        city=city, state=state, tz=tz, zip=zip3 + f"{w.rng.randint(0, 99):02d}",
        shop_type=w.pick_pairs(V.SHOP_TYPES), employees=employees, owner_first=first, owner_last=last,
        owner_email=email, phone=w.phone(), origin=origin, created=d, e=e, decay=1.0,
        plan_intent=plan_intent, stage="Lead", status="prospect", contact_ids=[], account_id=None,
        lead_source=None, deal_amount=None, anon_id=w.uuid(), card_risk=w.chance(0.10),
        pos=w.pick(V.POS_INTEGRATIONS, [0.3, 0.2, 0.12, 0.08, 0.05, 0.25]),
        brand=parent["brand"] if parent else re.sub(r"^The ", "", name), chain_id=None, internal=False,
        crm_name=name, crm_city=city,
    )
    shop["crm_legal"] = shop["legal_name"]
    if parent is not None:
        shop["phone"] = parent["phone"]
        if parent["chain_id"] is None:
            parent["chain_id"] = f"CH-{w.nid('chain', 1):03d}"
        shop["chain_id"] = parent["chain_id"]
        pool[parent["shop_id"]] = pool.get(parent["shop_id"], 1) + 1
        if pool[parent["shop_id"]] >= 4:
            del pool[parent["shop_id"]]
    elif domain and origin == "crm":
        pool[sid] = 1
    w.shops[sid] = shop
    return shop


def new_shop_name(w: World, city: str, state: str, last: str) -> str:
    """A believable candy-shop name that is unique within its state."""
    roll = w.rng.random()
    if roll < 0.28:
        name = f"{last}'s {w.pick(['Candy Shop', 'Sweet Shoppe', 'Confections', 'Candy Kitchen'])}"
    elif roll < 0.50:
        name = f"{city} {w.pick(['Candy Company', 'Candy Co.', 'Sweets', 'Confectionery'])}"
    else:
        word, suffix = w.pick(V.SWEET_WORDS), w.pick(V.SHOP_SUFFIXES)
        if "Candy" in word and "Candy" in suffix:
            suffix = w.pick(["Sweets", "Confections", "Treats", "Sweet Shop"])
        name = f"{word} {suffix}"
        if w.chance(0.25):
            name = "The " + name
    names = w.index["shop_names"]
    key = (name, state)
    if key in names:
        name = f"{name} of {city}"
        key = (name, state)
        n = 2
        while key in names:
            name, key = f"{name} #{n}", (f"{name} #{n}", state)
            n += 1
    names[key] = True
    return name



# ---------------------------------------------------------------------------- contacts
def make_contact(w: World, shop: dict, ts: datetime, *, source: str, role: str = "owner",
                 dup_of: dict | None = None, campaign: dict | None = None) -> dict:
    f = w.fake
    w.ids["crm"] += w.rng.randint(0, 2)
    rid = w.nid("crm", 4_800_100)
    if dup_of is not None:
        first, last = dup_of["_first"], dup_of["_last"]
        email = dup_of["email"]
        if w.chance(0.45) and dup_of["_first"] in V.NICKNAMES:
            first = V.NICKNAMES[first]
        if w.chance(0.4):
            email = f"{first.lower()}{last.lower()}{w.rng.randint(1, 9)}@{w.pick(V.FREE_MAIL[:3])}"
        title = dup_of["job_title"]
        phone = dup_of["phone"] if w.chance(0.5) else ""
    elif role == "owner":
        first, last, email = shop["owner_first"], shop["owner_last"], shop["owner_email"]
        title = w.pick_pairs(V.CRM_JOB_TITLES)
        phone = shop["phone"] if w.chance(0.8) else ""
    else:
        first, last = f.first_name(), f.last_name()
        title = w.pick(["General Manager", "Store Manager", "Marketing Manager", "Buyer", "Operations Manager"])
        if shop["domain"] and w.chance(0.8):
            email = f"{first.lower()}.{last.lower()}@{shop['domain']}"
        else:
            email = f"{first.lower()}{last.lower()}{w.rng.randint(1, 99)}@{w.pick(V.FREE_MAIL[:4])}"
        email = re.sub(r"[^a-z0-9.@_+-]", "", email)
        phone = w.phone() if w.chance(0.6) else ""
    focus = w.pick(FOCUS)
    notes = ""
    if w.chance(0.5):
        notes = {
            "Trade Show": f"Met at booth. Interested in {focus}.",
            "Webinar": f"Attended growth webinar. Asked about {focus}.",
            "Referral": f"Referred by existing customer. Wants help with {focus}.",
            "Inbound Web": f"Filled out demo form. Mentioned {focus}.",
            "Paid Social": f"Clicked social ad. Curious about {focus}.",
            "Partner - Distributor": f"Intro from distributor rep. Focus: {focus}.",
            "Cold Outreach": f"Replied to sequence. Possible fit for {focus}.",
            "Organic Signup": "Signed up in product; synced from app.",
        }.get(source, "")
    row = dict(
        record_id=rid, email=email, first_name=first, last_name=last, phone=phone, job_title=title,
        lead_source=source, original_source_campaign=campaign["name"] if campaign and w.chance(0.7) else "",
        lifecycle_stage="Lead", lead_status="New", owner=w.pick(V.SALES_REPS), created_at=ts, last_modified=ts,
        last_contacted=None, sales_activities=0, deal_amount=None, close_date=None, app_account_id=None,
        do_not_email=w.chance(0.03), notes=notes, call_notes=[],
        # ground truth (never exported)
        _shop_id=shop["shop_id"], _first=first, _last=last, _dup=dup_of is not None,
    )
    w.add("crm_contacts", row)
    shop["contact_ids"].append(rid)
    return row


def _contacts(w: World, shop: dict, include_dups: bool = False):
    for rid in shop["contact_ids"]:
        c = w.t["crm_contacts"][rid]
        if include_dups or not c["_dup"]:
            yield c


# ---------------------------------------------------------------------------- arrivals
def source_weights(w: World, d: date) -> tuple[list[str], list[float]]:
    from . import marketing as M
    names, weights = [], []
    for name, (wt, _p, _ttc) in V.CRM_SOURCES.items():
        if name == "Trade Show":
            wt *= 9 if M.days_since_show(w, d) is not None else 0.08
        elif name == "Webinar":
            wt *= 2.6 if (M.days_since_webinar(w, d) or 99) <= 5 else 0.45
        names.append(name)
        weights.append(wt)
    return names, weights


def arrivals(w: World, d: date) -> None:
    from . import marketing as M
    lam = CRM_BASE_RATE * growth(d) * DOW_B2B[d.weekday()]
    for _ in range(w.poisson(lam)):
        shop = make_shop(w, d, "crm")
        ts = w.moment(d)
        names, weights = source_weights(w, d)
        source = w.pick(names, weights)
        shop["lead_source"] = source
        campaign = M.campaign_for_source(w, source, d)
        owner = make_contact(w, shop, ts, source=source, campaign=campaign)
        owner["_campaign_id"] = campaign["campaign_id"] if campaign else None
        M.on_contact_created(w, shop, owner, ts, campaign)
        _plan_journey(w, shop, d)
        if w.chance(0.24):
            w.schedule(ts + timedelta(days=w.rng.uniform(3, 60)), "crm_add_contact", shop_id=shop["shop_id"])
        if w.chance(0.06):
            w.schedule(ts + timedelta(days=w.rng.uniform(0.2, 30)), "crm_add_dup", shop_id=shop["shop_id"])

    if d >= APP_LAUNCH:
        for _ in range(w.poisson(SELF_SERVE_RATE * growth(d))):
            _self_serve_signup(w, d)


def _plan_journey(w: World, shop: dict, d: date) -> None:
    source = shop["lead_source"]
    _wt, p_conv, ttc_median = V.CRM_SOURCES[source]
    p = 0.93 * p_conv * (0.8 + min(shop["employees"], 20) / 50)
    base = w.moment(d)
    if w.chance(p):
        ttc = max(3.0, w.lognorm(ttc_median, 0.55))
        due = base + timedelta(days=ttc)
        if due.date() < APP_LAUNCH:
            due = w.moment(APP_LAUNCH + timedelta(days=w.rng.randint(0, 40)))
            ttc = max(3.0, (due - base).total_seconds() / 86400)
        for frac, stage in [(0.12, "MQL"), (0.4, "SQL"), (0.7, "Opportunity")]:
            w.schedule(base + timedelta(days=max(0.5, ttc * frac)), "crm_stage", shop_id=shop["shop_id"], stage=stage)
        w.schedule(due, "convert", shop_id=shop["shop_id"])
    else:
        stage = w.pick(["Lead", "MQL", "SQL", "Opportunity", "Other"], [0.34, 0.25, 0.17, 0.09, 0.15])
        path = ["Lead", "MQL", "SQL", "Opportunity", "Other"]
        t = base
        for st in path[1: path.index(stage) + 1]:
            t = t + timedelta(days=w.rng.uniform(2, 14))
            w.schedule(t, "crm_stage", shop_id=shop["shop_id"], stage=st)


def _self_serve_signup(w: World, d: date) -> None:
    from . import app as A
    shop = make_shop(w, d, "self_serve")
    shop["lead_source"] = "Organic Signup"
    shop["plan_intent"] = w.pick(V.PLAN_ORDER, [0.72, 0.23, 0.05])
    ts = w.moment(d, 0, 23.9)
    A.create_account(w, shop, ts, "self_serve")
    if w.chance(0.28):  # marketing automation syncs some signups into the CRM
        w.schedule(ts + timedelta(days=w.rng.uniform(1, 20)), "crm_add_selfserve", shop_id=shop["shop_id"])


# ---------------------------------------------------------------------------- handlers
@handler("crm_add_contact")
def _add_contact(w: World, due: datetime, shop_id: str) -> None:
    shop = w.shops[shop_id]
    c = make_contact(w, shop, due, source=shop["lead_source"], role="staff")
    c["lifecycle_stage"] = shop["stage"]
    c["lead_status"] = "Open"
    if shop["account_id"] and w.chance(0.8):
        c["app_account_id"] = shop["account_id"]


@handler("crm_add_dup")
def _add_dup(w: World, due: datetime, shop_id: str) -> None:
    shop = w.shops[shop_id]
    originals = [c for c in _contacts(w, shop)]
    if not originals:
        return
    src = w.pick(list(V.CRM_SOURCES))
    make_contact(w, shop, due, source=src, dup_of=originals[0])


@handler("crm_add_selfserve")
def _add_selfserve(w: World, due: datetime, shop_id: str) -> None:
    shop = w.shops[shop_id]
    c = make_contact(w, shop, due, source="Organic Signup")
    c["lifecycle_stage"] = "Customer"
    c["lead_status"] = "Connected"
    c["app_account_id"] = shop["account_id"] if w.chance(0.75) else None
    c["close_date"] = due.date()
    c["last_contacted"] = None


@handler("crm_stage")
def _stage(w: World, due: datetime, shop_id: str, stage: str) -> None:
    from . import marketing as M
    shop = w.shops[shop_id]
    if shop["status"] != "prospect":
        return
    shop["stage"] = stage
    if stage == "Opportunity":
        plan = V.PLANS[shop["plan_intent"]]
        shop["deal_amount"] = round(plan["annual"] / 100 * w.pick([1.0, 1.0, 0.9, 0.8]), 2)
    for c in _contacts(w, shop):
        c["lifecycle_stage"] = stage
        c["lead_status"] = {
            "Lead": w.pick(["New", "Open", "Attempted to Contact"]),
            "MQL": w.pick(["Open", "Attempted to Contact", "Connected"]),
            "SQL": w.pick(["In Progress", "Connected"]),
            "Opportunity": "In Progress",
            "Other": w.pick(["Closed Lost", "Closed Lost", "Unqualified"]),
        }[stage]
        c["last_modified"] = due
        if stage != "Lead":
            c["sales_activities"] += w.rng.randint(1, 4)
            c["last_contacted"] = due - timedelta(hours=w.rng.uniform(1, 70))
        if stage in ("Opportunity", "Other") and shop["deal_amount"]:
            c["deal_amount"] = shop["deal_amount"]
        if stage == "Other":
            c["close_date"] = due.date()
    if stage in V.CALL_NOTES and w.chance(0.6):
        _note(w, shop, due, w.pick(V.CALL_NOTES[stage]))
    if stage == "Other":
        _note(w, shop, due, "LOST: " + fill(w.pick(V.LOST_REASONS), competitor=w.pick(V.COMPETITORS), pos=shop["pos"].title()))
    M.on_stage(w, shop, stage, due)


def _note(w: World, shop: dict, due: datetime, template: str) -> None:
    text = fill(template, pos=shop["pos"].title() if shop["pos"] != "none" else "a spreadsheet",
                leadtype=w.pick(list(V.LEAD_TYPES)).replace("_", " "), plan=shop["plan_intent"].title(),
                competitor=w.pick(V.COMPETITORS), discount=w.pick([10, 15, 20]))
    for c in _contacts(w, shop):
        c["call_notes"].append(f"[{due:%m/%d}] {text}")
        break


@handler("convert")
def _convert(w: World, due: datetime, shop_id: str) -> None:
    from . import app as A
    shop = w.shops[shop_id]
    if shop["status"] != "prospect":
        return
    acct = A.create_account(w, shop, due, "sales_assisted")
    for c in _contacts(w, shop):
        c["lifecycle_stage"] = "Customer"
        c["lead_status"] = "Connected"
        c["close_date"] = due.date()
        c["last_modified"] = due
        c["deal_amount"] = shop["deal_amount"] or round(V.PLANS[acct["plan_id"]]["annual"] / 100, 2)
        if w.chance(0.85):
            c["app_account_id"] = acct["account_id"]


def make_internal_shop(w: World, d: date) -> dict:
    """A staff-owned demo/QA shop. It exists in the app, billing and support but is not a real customer."""
    shop = make_shop(w, d, "internal")
    first, last = w.fake.first_name(), w.fake.last_name()
    shop.update(
        name=w.pick(["TEST - Demo Candy Co", "QA Sandbox Sweets", "Acme Gummies (demo)", "TEST Shop - do not use", "Sales Demo Confections"]),
        owner_first=first, owner_last=last, owner_email=f"{first.lower()}.{last.lower()}@sweetreach.example", domain=None,
        internal=True, plan_intent="pro", e=1.0, card_risk=False, lead_source="Internal", employees=3)
    shop["crm_name"], shop["legal_name"], shop["crm_legal"] = shop["name"], shop["name"], shop["name"]
    return shop
