"""Source 4 - Parquet exports from the billing system (Stripe-like): customers, subscriptions,
invoices and payment attempts. Money is integer cents; timestamps are UTC; ids are opaque strings.

The only link back to the app is `metadata.app_account_id`, which is missing on some rows - the
combined pipeline has to fall back to the billing customer id stored on the app account.
"""
from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ..sim.world import World

TS = pa.timestamp("us", tz="UTC")
META = pa.struct([("app_account_id", pa.string())])

SCHEMAS = {
    "customers": pa.schema([
        ("customer_id", pa.string()), ("email", pa.string()), ("name", pa.string()), ("created_at", TS),
        ("updated_at", TS), ("delinquent", pa.bool_()),
        ("default_card", pa.struct([("brand", pa.string()), ("last4", pa.string()), ("exp", pa.string())])),
        ("address", pa.struct([("city", pa.string()), ("state", pa.string())])), ("metadata", META)]),
    "subscriptions": pa.schema([
        ("subscription_id", pa.string()), ("customer_id", pa.string()), ("status", pa.string()), ("plan_code", pa.string()),
        ("billing_interval", pa.string()), ("unit_amount_cents", pa.int64()), ("started_at", TS),
        ("current_period_start", TS), ("current_period_end", TS), ("cancel_at_period_end", pa.bool_()),
        ("canceled_at", TS), ("ended_at", TS),
        ("cancellation_details", pa.struct([("reason", pa.string()), ("feedback", pa.string()), ("comment", pa.string())])),
        ("discount", pa.struct([("code", pa.string()), ("percent_off", pa.int32()), ("cycles_remaining", pa.int32())])),
        ("metadata", META), ("updated_at", TS)]),
    "invoices": pa.schema([
        ("invoice_id", pa.string()), ("number", pa.string()), ("customer_id", pa.string()), ("subscription_id", pa.string()),
        ("status", pa.string()), ("currency", pa.string()), ("plan_code", pa.string()), ("billing_interval", pa.string()),
        ("billing_reason", pa.string()), ("subtotal_cents", pa.int64()), ("discount_cents", pa.int64()),
        ("tax_cents", pa.int64()), ("total_cents", pa.int64()), ("amount_paid_cents", pa.int64()), ("amount_refunded_cents", pa.int64()),
        ("discount_code", pa.string()), ("created_at", TS), ("period_start", TS), ("period_end", TS),
        ("due_date", pa.date32()), ("paid_at", TS), ("attempt_count", pa.int32()), ("metadata", META), ("updated_at", TS)]),
    "payments": pa.schema([
        ("payment_id", pa.string()), ("invoice_id", pa.string()), ("customer_id", pa.string()), ("amount_cents", pa.int64()),
        ("currency", pa.string()), ("status", pa.string()), ("failure_code", pa.string()), ("attempt_number", pa.int32()),
        ("attempted_at", TS), ("card_brand", pa.string()), ("card_last4", pa.string())]),
}


def _customer(r: dict) -> dict:
    return dict(customer_id=r["customer_id"], email=r["email"], name=r["name"], created_at=r["created_at"],
                updated_at=r["updated_at"], delinquent=r["delinquent"],
                default_card=dict(brand=r["card_brand"], last4=r["card_last4"], exp=r["card_exp"]),
                address=dict(city=r["address_city"], state=r["address_state"]),
                metadata=dict(app_account_id=r["metadata_app_account_id"]))


def _subscription(r: dict) -> dict:
    d = dict(r)
    d["status"] = r["status"]
    d["discount"] = dict(code=r["discount_code"], percent_off=r["discount_percent_off"], cycles_remaining=r["discount_cycles_remaining"])
    d["metadata"] = dict(app_account_id=r["metadata_app_account_id"])
    cd = r.get("cancellation_details")
    d["cancellation_details"] = dict(reason=cd["reason"], feedback=cd["feedback"], comment=cd["comment"]) if cd else None
    return d


def _invoice(r: dict) -> dict:
    d = dict(r)
    d["metadata"] = dict(app_account_id=r["metadata_app_account_id"])
    return d


def write(w: World, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "customers": (sorted(w.t["bill_customers"].values(), key=lambda r: (r["created_at"], r["customer_id"])), _customer),
        "subscriptions": (sorted(w.t["bill_subscriptions"].values(), key=lambda r: (r["started_at"], r["subscription_id"])), _subscription),
        "invoices": (sorted(w.t["bill_invoices"].values(), key=lambda r: (r["created_at"], r["invoice_id"])), _invoice),
        "payments": (sorted(w.t["bill_payments"].values(), key=lambda r: (r["attempted_at"], r["payment_id"])), dict),
    }
    counts = {}
    for name, (rows, fn) in spec.items():
        schema = SCHEMAS[name]
        records = [{f.name: fn(r)[f.name] for f in schema} for r in rows]
        pq.write_table(pa.Table.from_pylist(records, schema=schema), out_dir / f"{name}.parquet", compression="zstd")
        counts[name] = len(records)
    return counts
