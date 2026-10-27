"""The SweetReach application database: accounts (candy shops), their users, the buyer leads the
app finds for them, the campaigns they run and the orders that result."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .. import vocab as V
from .text import fill, typo
from .world import World, handler

LEAD_BASE = 0.05       # leads per active-account-day (before engagement/plan scaling)
CAMPAIGN_BASE = 0.011
ORGANIC_ORDER_BASE = 0.0032
PLAN_ACTIVITY = {"starter": 0.8, "growth": 1.0, "pro": 1.5}
LEAD_STATUS_FLOW = ("new", "contacted", "quoted", "won", "lost")
ACTIVE_STATES = ("trialing", "active", "past_due")


def seed_static(w: World) -> None:
    for pid, p in V.PLANS.items():
        w.add("app_plans", dict(plan_id=pid, name=p["name"], monthly_price_cents=p["monthly"],
                                annual_price_cents=p["annual"], lead_limit=p["lead_limit"],
                                campaign_limit=p["campaign_limit"], seat_limit=p["seat_limit"]))
    for i, (sku, name, cat, price, months) in enumerate(V.PRODUCTS, start=1):
        w.add("app_products", dict(
            product_id=i, sku=sku, name=name, category=cat, list_price=price, unit_cost=round(price * 0.52, 2),
            season=",".join(str(m) for m in months) if months else None))
    for agent_i, (name, group) in enumerate(V.AGENTS, start=1):
        from .support import seed_agent
        seed_agent(w, agent_i, name, group)


# ---------------------------------------------------------------------------- accounts
def create_account(w: World, shop: dict, ts: datetime, signup_source: str, *, primary: bool = True) -> dict:
    from . import marketing as M
    aid = w.nid("account", 5001)
    plan = shop["plan_intent"]
    acct = w.add("app_accounts", dict(
        account_id=aid, name=shop["name"], slug=f"{shop['name'].lower().replace(' ', '-').replace(chr(39), '')}-{aid}"[:60],
        plan_id=plan, status="trialing", signup_source=signup_source, shop_type=shop["shop_type"], city=shop["city"],
        state=shop["state"], postal_code=shop["zip"], timezone=shop["tz"], employees=shop["employees"],
        billing_customer_id=None, created_at=ts, trial_ends_at=ts + timedelta(days=14), churned_at=None,
        churn_reason=None, merged_into_account_id=None, deleted_at=None, updated_at=ts,
        settings=dict(integration=shop["pos"], sms_enabled=plan != "starter" or w.chance(0.4),
                      service_radius_miles=w.pick([10, 15, 25, 40, 60]), brand_color=w.pick(["#e91e63", "#ff9800", "#7b1fa2", "#00acc1", "#43a047"])),
        _shop_id=shop["shop_id"], _primary=primary, _true_churn_reason=None))
    w.index["acct_shop"][aid] = shop["shop_id"]
    w.index["acct_users"][aid] = []
    first, last = shop["owner_first"], shop["owner_last"]
    email = shop["owner_email"]
    if not primary or (not shop["internal"] and w.chance(0.12)):   # signs up with a personal address instead
        email = f"{first.lower()}{last.lower()}{w.rng.randint(1, 99) if not primary else ''}@{w.pick(V.FREE_MAIL[:3])}"
    _add_user(w, acct, ts, "owner", f"{first} {last}", email)
    w.schedule(acct["trial_ends_at"], "trial_end", account_id=aid)
    if not primary:
        shop.setdefault("extra_accounts", []).append(aid)
        return acct
    shop["account_id"] = aid
    shop["status"] = "customer"
    cap = V.PLANS[plan]["seat_limit"] - 1
    for _ in range(min(cap, w.poisson(2.6 * (1 + shop["employees"] / 10)))):
        w.schedule(ts + timedelta(days=w.rng.uniform(0.3, 45)), "add_user", account_id=aid)
    M.on_signup(w, shop, acct, ts)
    if not shop["internal"]:
        if w.chance(0.42):
            w.schedule(ts + timedelta(days=w.rng.uniform(40, 60)), "nps", account_id=aid)
        if w.mess(0.06):
            w.schedule(ts + timedelta(days=w.rng.uniform(60, 300)), "rebrand", account_id=aid)
        if w.mess(0.05):
            w.schedule(ts + timedelta(days=w.rng.uniform(40, 300)), "moved", account_id=aid)
        if w.mess(0.04):
            w.schedule(ts + timedelta(days=w.rng.uniform(5, 60)), "dup_signup", account_id=aid)
    return acct


def spawn_test_account(w: World, d: date) -> None:
    from . import crm
    shop = crm.make_internal_shop(w, d)
    create_account(w, shop, w.moment(d), "self_serve")


def _add_user(w: World, acct: dict, ts: datetime, role: str, name: str | None = None, email: str | None = None) -> dict:
    f = w.fake
    shop = w.shops[acct["_shop_id"]]
    if name is None:
        first, last = f.first_name(), f.last_name()
        name = f"{first} {last}"
        if shop["domain"] and w.chance(0.8):
            email = f"{first.lower()}.{last.lower()}@{shop['domain']}"
        else:
            email = f"{first.lower()}{last.lower()}{w.rng.randint(1, 99)}@{w.pick(V.FREE_MAIL[:4])}"
    uid = w.nid("user", 7001)
    row = w.add("app_users", dict(
        user_id=uid, account_id=acct["account_id"], email=email, full_name=name, role=role, is_active=True,
        created_at=ts, last_login_at=ts, updated_at=ts))
    w.index["acct_users"][acct["account_id"]].append(uid)
    return row


@handler("add_user")
def _h_add_user(w: World, due: datetime, account_id: int) -> None:
    acct = w.t["app_accounts"][account_id]
    if acct["status"] in ("churned", "merged"):
        return
    _add_user(w, acct, due, w.pick(["manager", "staff"], [0.35, 0.65]))


@handler("trial_end")
def _h_trial_end(w: World, due: datetime, account_id: int) -> None:
    from . import billing
    acct = w.t["app_accounts"][account_id]
    if acct["status"] != "trialing":
        return
    shop = w.shops[acct["_shop_id"]]
    if not acct["_primary"]:
        churn_account(w, acct, due, "duplicate_signup")
    elif shop["internal"] or w.chance(0.90 if acct["signup_source"] == "sales_assisted" else 0.72):
        billing.start_billing(w, acct, due)
    else:
        churn_account(w, acct, due, "trial_expired")


@handler("rebrand")
def _h_rebrand(w: World, due: datetime, account_id: int) -> None:
    from .crm import new_shop_name
    acct = w.t["app_accounts"][account_id]
    if acct["status"] in ("churned", "merged"):
        return
    shop = w.shops[acct["_shop_id"]]
    acct["name"] = shop["name"] = new_shop_name(w, shop["city"], shop["state"], shop["owner_last"])
    acct["updated_at"] = due     # the CRM, billing and support desk keep the old name


@handler("moved")
def _h_moved(w: World, due: datetime, account_id: int) -> None:
    acct = w.t["app_accounts"][account_id]
    if acct["status"] in ("churned", "merged"):
        return
    near = [c for c in V.CITIES if c[1] == acct["state"] and c[0] != acct["city"]]
    if near:
        shop = w.shops[acct["_shop_id"]]
        city, _st, _tz, zip3 = w.pick(near)
        acct["city"] = shop["city"] = city
        acct["postal_code"] = shop["zip"] = zip3 + f"{w.rng.randint(0, 99):02d}"
        acct["updated_at"] = due


@handler("dup_signup")
def _h_dup_signup(w: World, due: datetime, account_id: int) -> None:
    acct = w.t["app_accounts"][account_id]
    if acct["status"] in ("churned", "merged"):
        return
    dup = create_account(w, w.shops[acct["_shop_id"]], due, "self_serve", primary=False)
    w.schedule(due + timedelta(days=w.rng.uniform(3, 13)), "merge_account", dup_id=dup["account_id"], primary_id=account_id)


@handler("merge_account")
def _h_merge(w: World, due: datetime, dup_id: int, primary_id: int) -> None:
    dup = w.t["app_accounts"][dup_id]
    dup.update(status="merged", merged_into_account_id=primary_id, deleted_at=due, updated_at=due)
    for uid in w.index["acct_users"][dup_id]:   # support re-parents the users; leads/orders stay behind
        w.t["app_users"][uid]["account_id"] = primary_id
        w.t["app_users"][uid]["updated_at"] = due
        w.index["acct_users"][primary_id].append(uid)
    w.index["acct_users"][dup_id] = []


@handler("nps")
def _h_nps(w: World, due: datetime, account_id: int) -> None:
    import math
    acct = w.t["app_accounts"][account_id]
    if acct["status"] in ("churned", "merged"):
        return
    shop = w.shops[acct["_shop_id"]]
    score = int(round(min(10, max(0, 6.3 + 1.7 * math.log(max(shop["e"] * shop["decay"], 0.15)) + w.rng.gauss(0, 1.8)))))
    band = "promoter" if score >= 9 else "passive" if score >= 7 else "detractor"
    comment = None
    if w.chance(0.7):
        hol = V.upcoming_holiday(due.date(), 60)
        comment = typo(w, fill(w.pick(V.NPS_TEXT[band]), leadtype=w.pick(list(V.LEAD_TYPES)).replace("_", " "),
                               amount=int(w.lognorm(380, 0.5)), holiday=hol[0] if hol else "holiday",
                               pos=shop["pos"].title() if shop["pos"] != "none" else "our register", city=shop["city"]), 0.2)
    uids = w.index["acct_users"][account_id]
    w.add("app_nps", dict(response_id=w.nid("nps", 1), account_id=account_id, user_id=uids[0] if uids else None,
                          submitted_at=due, score=score, comment=comment))


def churn_account(w: World, acct: dict, ts: datetime, reason: str) -> None:
    acct["status"] = "churned"
    acct["churned_at"] = ts
    acct["_true_churn_reason"] = reason
    # what customer success *recorded* is not always what happened
    coded = reason
    if reason in V.EXIT_TEXT and w.mess(0.28):
        coded = w.pick(["other", None])
    acct["churn_reason"] = coded
    acct["updated_at"] = ts
    shop = w.shops[acct["_shop_id"]]
    shop["status"] = "churned"
    for uid in w.index["acct_users"][acct["account_id"]]:
        u = w.t["app_users"][uid]
        u["is_active"] = False
        u["updated_at"] = ts
    if reason in V.EXIT_TEXT and w.chance(0.7):
        _exit_survey(w, acct, shop, reason, ts)
    # sales rarely updates the CRM when a customer churns; only some records get synced later
    if w.chance(0.4):
        w.schedule(ts + timedelta(days=w.rng.uniform(1, 40)), "crm_churn_sync", shop_id=shop["shop_id"])


def _exit_survey(w: World, acct: dict, shop: dict, reason: str, ts: datetime) -> None:
    code = V.EXIT_CODES[reason]
    if w.mess(0.30):
        code = w.pick([V.EXIT_CODE_FALLBACK, V.EXIT_CODE_FALLBACK, w.pick(list(V.EXIT_CODES.values()))])
    text = None
    if not w.chance(0.12):
        won = sum(1 for l in w.t["app_leads"].values() if l["account_id"] == acct["account_id"] and l["status"] == "won")
        months = max(1, (ts - acct["created_at"]).days // 30)
        text = typo(w, fill(w.pick(V.EXIT_TEXT[reason]), price=V.PLANS[acct["plan_id"]]["monthly"] // 100, plan=acct["plan_id"].title(),
                            n=max(won, 1), months=months, competitor=w.pick(V.COMPETITORS), feature=w.pick(V.FEATURES),
                            pos=shop["pos"].title() if shop["pos"] != "none" else "our register", city=shop["city"],
                            leadtype=w.pick(list(V.LEAD_TYPES)).replace("_", " "), years=w.rng.randint(3, 30),
                            holiday=(V.upcoming_holiday(ts.date(), 60) or ("the holiday",))[0]), 0.18)
    rec = {"closing_shop": 7, "seasonal_pause": 8}.get(reason, 3)
    w.add("app_exit_surveys", dict(
        survey_id=w.nid("survey", 1), account_id=acct["account_id"], submitted_at=ts - timedelta(minutes=w.rng.uniform(2, 30)),
        reason_code=code, would_recommend=int(min(10, max(0, round(w.rng.gauss(rec, 2.2))))), free_text=text,
        _true_reason=reason))


@handler("crm_churn_sync")
def _h_crm_churn(w: World, due: datetime, shop_id: str) -> None:
    shop = w.shops[shop_id]
    for rid in shop["contact_ids"]:
        c = w.t["crm_contacts"][rid]
        if not c["_dup"]:
            c["lead_status"] = "Churned"
            c["last_modified"] = due


def touch_login(w: World, acct: dict, ts: datetime) -> None:
    uids = w.index["acct_users"][acct["account_id"]]
    if uids:
        u = w.t["app_users"][w.pick(uids)]
        if u["is_active"] and ts > u["last_login_at"]:
            u["last_login_at"] = ts


# ---------------------------------------------------------------------------- leads
def _org_name(w: World, lead_type: str, city: str) -> str:
    f = w.fake
    last, first = f.last_name(), f.first_name()
    return {
        "school_pta": w.pick([f"{last} Elementary PTA", f"{city} Middle School Boosters", f"{last} High School Band Boosters"]),
        "corporate_office": f"{last} {w.pick(V.BIZ_KINDS)}" if w.chance(0.6) else f"{w.pick(V.WORDS_BIZ)} {w.pick(V.BIZ_KINDS)}",
        "wedding_planner": w.pick([f"{last} Weddings & Events", f"{first} {last} Wedding Co.", f"Blissful Day Events - {city}"]),
        "church_nonprofit": w.pick([f"St. {first} Parish Festival", f"{city} Rotary Club", f"{city} Animal Rescue League", f"{last} Community Church"]),
        "birthday_party": f"{first} {last} - {w.pick(V.PARTY_TYPES)}",
        "hotel_restaurant": w.pick([f"{last} Inn", f"The {w.pick(V.WORDS_BIZ)} Bistro", f"{city} Grand Hotel"]),
        "sports_team": w.pick([f"{city} {w.pick(V.MASCOTS)} Youth League", f"{last} Travel Soccer", f"{city} Little League"]),
        "realtor": f"{first} {last} Realty",
        "festival_vendor": w.pick([f"{city} Fall Festival", f"{city} Farmers Market", f"{last} County Fair"]),
    }[lead_type]


def create_lead(w: World, acct: dict, ts: datetime) -> dict:
    d = ts.date()
    shop = w.shops[acct["_shop_id"]]
    types = list(V.LEAD_TYPES)
    weights = [V.LEAD_TYPES[t]["w"] * V.LEAD_TYPES[t]["months"][d.month - 1] for t in types]
    lt = w.pick(types, weights)
    spec = V.LEAD_TYPES[lt]
    city, state, _tz, zip3 = (acct["city"], acct["state"], None, acct["postal_code"][:3])
    if w.chance(0.3):
        near = [c for c in V.CITIES if c[1] == acct["state"]]
        city, state, _tz, zip3 = w.pick(near)
    score = int(min(99, max(5, w.rng.gauss(55, 18))))
    est = round(w.lognorm(spec["value"], 0.45), -1)
    uids = w.index["acct_users"][acct["account_id"]]
    lead = w.add("app_leads", dict(
        lead_id=w.nid("lead", 100001), account_id=acct["account_id"], assigned_user_id=w.pick(uids) if uids else None,
        org_name=_org_name(w, lt, city), contact_name=w.fake.name(), lead_type=lt,
        source=w.pick_pairs(V.LEAD_SOURCES), city=city, state=state, postal_code=zip3 + f"{w.rng.randint(0, 99):02d}",
        score=score, status="new", est_order_value=est, created_at=ts, updated_at=ts, notes=None,
        attributes=dict(event_month=(d + timedelta(days=w.rng.randint(14, 120))).strftime("%Y-%m"),
                        headcount=int(w.lognorm(60, 0.8)), matched_keywords=w.pick(
                            [["fundraiser", "bulk"], ["wedding", "favors"], ["gift", "corporate"], ["party", "candy bar"], ["festival", "vendor"]]))))
    if w.chance(0.3):
        product = w.pick(["lollipops", "gummy bears", "chocolate favors", "candy bags", "fudge", "saltwater taffy", "gift boxes"])
        lead["notes"] = typo(w, fill(w.pick(V.LEAD_NOTES), first=lead["contact_name"].split()[0], qty=w.pick([50, 100, 150, 200, 300, 500]),
                                     product=product, event=w.pick(V.LEAD_NOTE_EVENTS), day=w.pick(["3rd", "12th", "20th", "Oct 3", "Nov 14"]),
                                     amount=int(est), n=w.pick([12, 25, 40, 60])), 0.3)
    # outcome plan
    p_contact, p_quote = 0.92, 0.62
    e = shop["e"] * shop["decay"]
    t = ts
    contacted = w.chance(p_contact)
    quoted = False
    if contacted:
        t = ts + timedelta(hours=w.lognorm(6, 1.0))
        w.schedule(t, "lead_status", lead_id=lead["lead_id"], status="contacted")
        quoted = w.chance(p_quote)
        if quoted:
            t = t + timedelta(days=w.rng.uniform(1, 6))
            w.schedule(t, "lead_status", lead_id=lead["lead_id"], status="quoted")
    p_win = spec["win"] * (0.5 + score / 100) * min(1.4, e ** 0.15) * (1.0 if quoted else 0.4 if contacted else 0.0)
    outcome_t = t + timedelta(days=w.rng.uniform(3, 25))
    if contacted:
        w.schedule(outcome_t, "lead_outcome", lead_id=lead["lead_id"], won=w.chance(min(0.85, p_win)))
    return lead


@handler("lead_status")
def _h_lead_status(w: World, due: datetime, lead_id: int, status: str) -> None:
    lead = w.t["app_leads"][lead_id]
    if lead["status"] in ("won", "lost"):
        return
    lead["status"] = status
    lead["updated_at"] = due


@handler("lead_outcome")
def _h_lead_outcome(w: World, due: datetime, lead_id: int, won: bool) -> None:
    lead = w.t["app_leads"][lead_id]
    lead["status"] = "won" if won else "lost"
    lead["updated_at"] = due
    if won:
        acct = w.t["app_accounts"][lead["account_id"]]
        spec = V.LEAD_TYPES[lead["lead_type"]]
        create_order(w, acct, due, spec["order_type"], "lead", lead=lead, target=lead["est_order_value"])
        touch_login(w, acct, due)


# ---------------------------------------------------------------------------- orders
def _product_weights(products: list[dict], d: date, order_type: str) -> list[float]:
    out = []
    for p in products:
        cat, months = p["category"], p["season"]
        wt = V.CATEGORY_BASE_WEIGHT[cat]
        if months:
            wt *= 4.0 if str(d.month) in months.split(",") else 0.05
        if order_type == "gift_box" and cat in ("gift_box", "chocolate"):
            wt *= 3
        if order_type in ("bulk", "wholesale") and cat in ("gummies", "lollipops", "sour"):
            wt *= 1.8
        out.append(wt)
    return out


def create_order(w: World, acct: dict, ts: datetime, order_type: str, channel: str, *, lead: dict | None = None,
                 campaign: dict | None = None, target: float | None = None) -> dict:
    products = list(w.t["app_products"].values())
    n_items = {"retail": (1, 3), "bulk": (2, 6), "gift_box": (1, 3), "wholesale": (3, 8), "event": (2, 6)}[order_type]
    k = w.rng.randint(*n_items)
    weights = _product_weights(products, ts.date(), order_type)
    chosen, seen = [], set()
    while len(chosen) < k:
        p = w.pick(products, weights)
        if p["product_id"] not in seen:
            seen.add(p["product_id"])
            chosen.append(p)
    if target is None:
        target = {"retail": w.lognorm(42, 0.6), "bulk": w.lognorm(300, 0.5), "gift_box": w.lognorm(90, 0.5),
                  "wholesale": w.lognorm(800, 0.5), "event": w.lognorm(200, 0.6)}[order_type]
    per_item = target / k
    oid = w.nid("order", 200001)
    subtotal = 0.0
    for p in chosen:
        qty = max(1, round(per_item / p["list_price"] * w.rng.uniform(0.7, 1.3)))
        w.add("app_order_items", dict(order_item_id=w.nid("order_item", 1), order_id=oid, product_id=p["product_id"],
                                      quantity=qty, unit_price=p["list_price"]))
        subtotal += qty * p["list_price"]
    discount = round(subtotal * w.pick([0.05, 0.10, 0.15]), 2) if w.chance(0.12) else 0.0
    order = w.add("app_orders", dict(
        order_id=oid, account_id=acct["account_id"], lead_id=lead["lead_id"] if lead else None,
        campaign_id=campaign["campaign_id"] if campaign else None, ordered_at=ts, order_type=order_type,
        channel=channel, status="processing", subtotal=round(subtotal, 2), discount=discount,
        total=round(subtotal - discount, 2), item_count=k, updated_at=ts))
    w.schedule(ts + timedelta(hours=w.rng.uniform(2, 70)), "order_status", order_id=oid,
               status=w.pick(["fulfilled", "refunded", "cancelled"], [0.95, 0.03, 0.02]))
    return order


@handler("order_status")
def _h_order_status(w: World, due: datetime, order_id: int, status: str) -> None:
    o = w.t["app_orders"][order_id]
    o["status"] = status
    o["updated_at"] = due


@handler("campaign_order")
def _h_campaign_order(w: World, due: datetime, account_id: int, campaign_id: int) -> None:
    acct = w.t["app_accounts"][account_id]
    camp = w.t["app_campaigns"][campaign_id]
    typ = w.pick(["retail", "bulk", "gift_box"], [0.5, 0.25, 0.25])
    create_order(w, acct, due, typ, "campaign", campaign=camp)


# ---------------------------------------------------------------------------- campaigns
def create_campaign(w: World, acct: dict, ts: datetime) -> dict:
    d = ts.date()
    shop = w.shops[acct["_shop_id"]]
    hol = V.upcoming_holiday(d, 40)
    generic = {12: "Winter Warm-Up", 1: "Winter Warm-Up", 2: "Winter Warm-Up", 3: "Spring Refresh", 4: "Spring Refresh",
               5: "Spring Refresh", 6: "Summer Treats", 7: "Summer Treats", 8: "Summer Treats", 9: "Fall Favorites",
               10: "Fall Favorites", 11: "Fall Favorites"}[d.month]
    theme = hol[0] if hol and w.chance(0.8) else w.pick([generic, "Customer Appreciation", "Weekend"])
    channel = w.pick_pairs(V.CAMPAIGN_CHANNELS)
    offer = w.pick(V.CAMPAIGN_OFFERS)
    audience = int(min(8000, max(40, w.lognorm(260, 0.8) * (shop["e"] * shop["decay"]) ** 0.4)))
    uids = w.index["acct_users"][acct["account_id"]]
    lead_types = [t for t in V.LEAD_TYPES if w.chance(0.4)] or ["school_pta"]
    camp = w.add("app_campaigns", dict(
        campaign_id=w.nid("campaign", 3001), account_id=acct["account_id"], created_by_user_id=w.pick(uids) if uids else None,
        name=f"{theme} {offer}", channel=channel, season_tag=hol[0] if hol else None, status="sending",
        audience_size=audience, delivered=None, opens=None, clicks=None, unsubscribes=None,
        sent_at=ts, created_at=ts - timedelta(hours=w.rng.uniform(1, 48)),
        audience_filter=dict(lead_types=lead_types, radius_miles=acct["settings"]["service_radius_miles"],
                             min_score=w.pick([0, 40, 60]))))
    w.schedule(ts + timedelta(days=3), "campaign_results", campaign_id=camp["campaign_id"])
    return camp


@handler("campaign_results")
def _h_campaign_results(w: World, due: datetime, campaign_id: int) -> None:
    c = w.t["app_campaigns"][campaign_id]
    ch = c["channel"]
    aud = c["audience_size"]
    delivered = int(aud * {"email": 0.965, "sms": 0.985, "social": 1.0, "direct_mail": 0.93}[ch] * w.rng.uniform(0.97, 1.0))
    ctr = {"email": w.rng.uniform(0.02, 0.06), "sms": w.rng.uniform(0.05, 0.12), "social": w.rng.uniform(0.01, 0.035),
           "direct_mail": w.rng.uniform(0.01, 0.03)}[ch]
    c.update(delivered=delivered, clicks=int(delivered * ctr),
             opens=int(delivered * w.rng.uniform(0.2, 0.38)) if ch == "email" else None,
             unsubscribes=int(delivered * w.rng.uniform(0.0005, 0.004)) if ch in ("email", "sms") else None,
             status="sent")
    acct = w.t["app_accounts"][c["account_id"]]
    n_orders = w.poisson(c["clicks"] * 0.04 * (0.6 + 0.4 * V.season_factor(c["sent_at"].date())))
    for _ in range(n_orders):
        w.schedule(c["sent_at"] + timedelta(days=w.rng.uniform(0.2, 7), hours=w.rng.uniform(0, 12)), "campaign_order",
                   account_id=acct["account_id"], campaign_id=campaign_id)


# ---------------------------------------------------------------------------- daily
def daily(w: World, d: date) -> None:
    sf = V.season_factor(d)
    csf = V.campaign_season_factor(d)
    dow = d.weekday()
    weekday_f = [1.1, 1.1, 1.1, 1.1, 1.0, 0.55, 0.45][dow]
    order_dow = [0.8, 0.8, 0.85, 0.9, 1.1, 1.5, 1.3][dow]
    for acct in w.t["app_accounts"].values():
        if acct["status"] not in ACTIVE_STATES:
            continue
        shop = w.shops[acct["_shop_id"]]
        age = (d - acct["created_at"].date()).days
        ramp = min(1.0, 0.35 + age / 30)
        e = shop["e"] * shop["decay"] * PLAN_ACTIVITY[acct["plan_id"]] * ramp
        active_today = False
        for _ in range(w.poisson(LEAD_BASE * e * (0.7 + 0.3 * sf) * weekday_f)):
            create_lead(w, acct, w.moment(d))
            active_today = True
        for _ in range(w.poisson(CAMPAIGN_BASE * e * csf * weekday_f)):
            create_campaign(w, acct, w.moment(d, 8, 17))
            active_today = True
        for _ in range(w.poisson(ORGANIC_ORDER_BASE * e * sf * order_dow)):
            typ = w.pick(["retail", "bulk", "gift_box"], [0.65, 0.12, 0.23])
            create_order(w, acct, w.moment(d, 9, 20), typ, w.pick(["storefront", "phone", "online"], [0.4, 0.15, 0.45]))
            active_today = True
        if active_today or w.chance(0.04 * min(e, 2)):
            touch_login(w, acct, w.moment(d))
