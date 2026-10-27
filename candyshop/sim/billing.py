"""Stripe-style billing: customers, subscriptions, invoices, payment attempts and churn.

Churn is driven by engagement (low-engagement shops churn more), and a shop that has decided to
leave stops using the app well before its last invoice - that is the signal the combined dataset
is meant to expose.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from .. import vocab as V
from .world import World, handler

BASE_MONTHLY_HAZARD = 0.035
BASE_ANNUAL_HAZARD = 0.14
FIRST_ATTEMPT_OK = 0.955


def add_months(dt: datetime, months: int) -> datetime:
    m = dt.month - 1 + months
    y, m = dt.year + m // 12, m % 12 + 1
    return dt.replace(year=y, month=m, day=min(dt.day, calendar.monthrange(y, m)[1]))


def _price(plan: str, interval: str) -> int:
    return V.PLANS[plan]["annual" if interval == "year" else "monthly"]


def start_billing(w: World, acct: dict, ts: datetime) -> None:
    shop = w.shops[acct["_shop_id"]]
    cust_id = w.token("cus_")
    acct["billing_customer_id"] = cust_id
    acct["status"] = "active"
    acct["updated_at"] = ts
    owner = w.t["app_users"][w.index["acct_users"][acct["account_id"]][0]]
    billing_email = owner["email"] if w.chance(0.8) else f"accounting@{shop['domain']}" if shop["domain"] else owner["email"]
    brand = w.pick(["visa", "mastercard", "amex", "discover"], [0.5, 0.3, 0.15, 0.05])
    w.add("bill_customers", dict(
        customer_id=cust_id, email=billing_email, name=shop["legal_name"], created_at=ts, card_brand=brand,
        card_last4=f"{w.rng.randint(0, 9999):04d}", card_exp=f"{w.rng.randint(1, 12):02d}/{(ts.year + w.rng.randint(1, 4)) % 100:02d}",
        address_city=shop["city"], address_state=shop["state"], delinquent=False,
        metadata_app_account_id=None if w.mess(0.10) else str(acct["account_id"]), updated_at=ts,
        _account_id=acct["account_id"]))
    interval = "year" if w.chance(0.15) and not shop["internal"] else "month"
    code, pct, cycles = None, 0, 0
    src = shop["lead_source"]
    if acct["signup_source"] == "sales_assisted":
        if src in ("Trade Show", "Webinar") and w.chance(0.5):
            code, pct, cycles = "EXPO20", 20, 3
        elif src == "Referral" and w.chance(0.6):
            code, pct, cycles = "FRIEND15", 15, 2
        elif src == "Partner - Distributor" and w.chance(0.5):
            code, pct, cycles = "PARTNER10", 10, 12
    if shop["internal"]:
        code, pct, cycles = "INTERNAL", 100, 9999
    elif code is None and w.chance(0.08):
        code, pct, cycles = "WINBACK10", 10, 2
    sub_id = w.token("sub_")
    w.add("bill_subscriptions", dict(
        subscription_id=sub_id, customer_id=cust_id, status="active", plan_code=acct["plan_id"], billing_interval=interval,
        unit_amount_cents=_price(acct["plan_id"], interval), started_at=ts, current_period_start=ts,
        current_period_end=add_months(ts, 12 if interval == "year" else 1), cancel_at_period_end=False, canceled_at=None,
        ended_at=None, cancellation_details=None, discount_code=code, discount_percent_off=pct or None, discount_cycles_remaining=cycles or None,
        metadata_app_account_id=str(acct["account_id"]), updated_at=ts, _account_id=acct["account_id"], _pending_plan=None,
        _n_invoices=0))
    w.schedule(ts, "bill", sub_id=sub_id)


def _fail_code(w: World) -> str:
    return w.pick_pairs(V.TICKET_FAILURE_CODES)


@handler("bill")
def _h_bill(w: World, due: datetime, sub_id: str) -> None:
    sub = w.t["bill_subscriptions"][sub_id]
    if sub["status"] == "canceled":
        return
    acct = w.t["app_accounts"][sub["_account_id"]]
    shop = w.shops[acct["_shop_id"]]
    cust = w.t["bill_customers"][sub["customer_id"]]
    if sub["_pending_plan"]:
        sub["plan_code"] = sub["_pending_plan"]
        sub["unit_amount_cents"] = _price(sub["plan_code"], sub["billing_interval"])
        sub["_pending_plan"] = None
        acct["plan_id"] = sub["plan_code"]
        acct["updated_at"] = due
    interval = sub["billing_interval"]
    start = due
    end = add_months(start, 12 if interval == "year" else 1)
    sub["current_period_start"], sub["current_period_end"], sub["updated_at"] = start, end, due
    sub["_n_invoices"] += 1
    n = sub["_n_invoices"]

    subtotal = sub["unit_amount_cents"]
    discount = 0
    if sub["discount_cycles_remaining"]:
        discount = round(subtotal * sub["discount_percent_off"] / 100)
        sub["discount_cycles_remaining"] -= 1
        if sub["discount_cycles_remaining"] == 0:
            sub["discount_cycles_remaining"] = None
    tax = round((subtotal - discount) * V.SAAS_TAX.get(shop["state"], 0.0))
    inv_id = w.token("in_")
    invoice = w.add("bill_invoices", dict(
        invoice_id=inv_id, number=f"SR-{due.year}-{w.nid('invoice_no', 1):06d}", customer_id=sub["customer_id"],
        subscription_id=sub_id, status="open", currency="usd", plan_code=sub["plan_code"], billing_interval=interval,
        subtotal_cents=subtotal, discount_cents=discount, tax_cents=tax, total_cents=subtotal - discount + tax,
        amount_paid_cents=0, amount_refunded_cents=0, discount_code=sub["discount_code"] if discount else None,
        billing_reason="subscription_create" if n == 1 else "subscription_cycle", created_at=due,
        period_start=start, period_end=end, due_date=due.date(), paid_at=None, attempt_count=0,
        metadata_app_account_id=None if w.mess(0.08) else str(acct["account_id"]), updated_at=due))
    w.schedule(due + timedelta(minutes=w.rng.uniform(1, 40)), "pay_attempt", invoice_id=inv_id, attempt=1)

    # --- renewal decision: does this shop stay for another period?
    e = shop["e"]
    h = (BASE_ANNUAL_HAZARD if interval == "year" else BASE_MONTHLY_HAZARD) / (e ** 0.85)
    if n <= 2 and interval == "month":
        h *= 1.5
    h = min(0.6 if interval == "year" else 0.30, max(0.006, h))
    if shop["internal"]:
        h = 0.0
    if w.chance(h):
        span = (end - start).total_seconds()
        w.schedule(start + timedelta(seconds=span * w.rng.uniform(0.3, 0.6)), "activity_drop", account_id=acct["account_id"])
        if w.chance(0.35):
            lead_days = w.rng.uniform(2, 12) if interval == "month" else w.rng.uniform(5, 30)
            w.schedule(end - timedelta(days=lead_days), "cancel_request", account_id=acct["account_id"])
        sub["cancel_at_period_end"] = True
        w.schedule(end, "sub_end", sub_id=sub_id, reason=w.pick_pairs(V.CHURN_REASONS))
    else:
        sub["cancel_at_period_end"] = False
        plan = sub["plan_code"]
        if plan != "pro" and w.chance(0.03 * min(2.5, e)):
            sub["_pending_plan"] = V.PLAN_ORDER[V.PLAN_ORDER.index(plan) + 1]
        elif plan != "starter" and w.chance(0.015 / e):
            sub["_pending_plan"] = V.PLAN_ORDER[V.PLAN_ORDER.index(plan) - 1]
        w.schedule(end, "bill", sub_id=sub_id)


@handler("pay_attempt")
def _h_pay(w: World, due: datetime, invoice_id: str, attempt: int) -> None:
    inv = w.t["bill_invoices"][invoice_id]
    if inv["status"] != "open":
        return
    sub = w.t["bill_subscriptions"][inv["subscription_id"]]
    cust = w.t["bill_customers"][inv["customer_id"]]
    acct = w.t["app_accounts"][sub["_account_id"]]
    shop = w.shops[acct["_shop_id"]]
    if shop["card_risk"]:
        p_ok = 0.55 if attempt == 1 else 0.72
    else:
        p_ok = FIRST_ATTEMPT_OK if attempt == 1 else 0.62
    ok = w.chance(p_ok)
    w.add("bill_payments", dict(
        payment_id=w.token("pi_"), invoice_id=invoice_id, customer_id=inv["customer_id"], amount_cents=inv["total_cents"],
        currency="usd", status="succeeded" if ok else "failed", failure_code=None if ok else _fail_code(w),
        attempt_number=attempt, attempted_at=due, card_brand=cust["card_brand"], card_last4=cust["card_last4"]))
    inv["attempt_count"] = attempt
    inv["updated_at"] = due
    if ok:
        inv["status"], inv["amount_paid_cents"], inv["paid_at"] = "paid", inv["total_cents"], due
        cust["delinquent"], cust["updated_at"] = False, due
        if inv["total_cents"] > 0 and w.mess(0.015):
            w.schedule(due + timedelta(days=w.rng.uniform(1, 20)), "refund", invoice_id=invoice_id, partial=w.chance(0.4))
        if sub["status"] == "past_due":
            sub["status"], sub["updated_at"] = "active", due
        if acct["status"] == "past_due":
            acct["status"], acct["updated_at"] = "active", due
        return
    cust["delinquent"], cust["updated_at"] = True, due
    sub["status"], sub["updated_at"] = "past_due", due
    if acct["status"] != "churned":
        acct["status"], acct["updated_at"] = "past_due", due
    if attempt == 1 and w.chance(0.4):
        w.schedule(due + timedelta(days=w.rng.uniform(0.2, 2.5)), "ticket_trigger", account_id=acct["account_id"],
                   area="billing", reason="payment_failed")
    if attempt < 3:
        w.schedule(due + timedelta(days=3 if attempt == 1 else 4), "pay_attempt", invoice_id=invoice_id, attempt=attempt + 1)
    else:
        inv["status"] = "uncollectible"
        _end_sub(w, sub, due, "payment_failed")


def _end_sub(w: World, sub: dict, ts: datetime, reason: str) -> None:
    from . import app
    if sub["status"] == "canceled":
        return
    sub.update(status="canceled", canceled_at=ts, ended_at=ts, updated_at=ts)
    acct = w.t["app_accounts"][sub["_account_id"]]
    if acct["status"] != "churned":
        app.churn_account(w, acct, ts, reason)
    cust = w.t["bill_customers"][sub["customer_id"]]
    cust["updated_at"] = ts


@handler("refund")
def _h_refund(w: World, due: datetime, invoice_id: str, partial: bool) -> None:
    inv = w.t["bill_invoices"][invoice_id]
    amount = inv["total_cents"] // 2 if partial else inv["total_cents"]
    inv["amount_refunded_cents"], inv["updated_at"] = amount, due
    w.add("bill_payments", dict(
        payment_id=w.token("pi_"), invoice_id=invoice_id, customer_id=inv["customer_id"], amount_cents=amount, currency="usd",
        status="refunded", failure_code=None, attempt_number=None, attempted_at=due, card_brand=None, card_last4=None))


@handler("sub_end")
def _h_sub_end(w: World, due: datetime, sub_id: str, reason: str) -> None:
    sub = w.t["bill_subscriptions"][sub_id]
    if reason in V.BILLING_CANCEL_ENUM and w.chance(0.35):   # filled in on the billing-portal cancel screen
        enum = V.BILLING_CANCEL_ENUM[reason] if not w.mess(0.2) else "other"
        sub["cancellation_details"] = dict(
            reason=enum, feedback=enum, comment=w.pick(V.BILLING_COMMENTS[reason]) if w.chance(0.6) else None, _true_reason=reason)
    _end_sub(w, sub, due, reason)


@handler("activity_drop")
def _h_activity_drop(w: World, due: datetime, account_id: int) -> None:
    acct = w.t["app_accounts"][account_id]
    if acct["status"] != "churned":
        w.shops[acct["_shop_id"]]["decay"] = 0.25


@handler("cancel_request")
def _h_cancel_request(w: World, due: datetime, account_id: int) -> None:
    acct = w.t["app_accounts"][account_id]
    if acct["status"] != "churned":
        from . import support
        support.create_account_ticket(w, due, acct, area="billing", reason="cancellation")
