"""Ground truth for the combined pipeline.

The five sources never share a clean key, but the simulation knows which records belong to which
candy shop. These files let `candy pipeline validate` score entity resolution honestly.
They are NOT a data source; a real project would not have them.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ..sim.world import World


def write(w: World, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    org_by_account = w.index["acct_org"]
    cust_by_account = {a["account_id"]: a["billing_customer_id"] for a in w.t["app_accounts"].values()}
    with open(out_dir / "crosswalk.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["shop_id", "shop_name", "state", "status", "app_account_id", "billing_customer_id", "support_org_id",
                     "crm_record_ids", "crm_duplicate_record_ids", "chain_id", "is_internal_test", "duplicate_app_account_ids"])
        for s in w.shops.values():
            crm = [r for r in s["contact_ids"] if not w.t["crm_contacts"][r]["_dup"]]
            dup = [r for r in s["contact_ids"] if w.t["crm_contacts"][r]["_dup"]]
            aid = s["account_id"]
            wr.writerow([s["shop_id"], s["name"], s["state"], s["status"], aid or "", cust_by_account.get(aid) or "",
                         org_by_account.get(aid, "") if aid else "", "|".join(map(str, crm)), "|".join(map(str, dup)), s["chain_id"] or "",
                         int(s["internal"]), "|".join(map(str, s.get("extra_accounts", [])))])
    with open(out_dir / "marketing_event_shop.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["event_id", "shop_id"])
        for e in w.t["mkt_events"].values():
            if e["_shop_id"]:
                wr.writerow([e["event_id"], e["_shop_id"]])
    with open(out_dir / "ticket_account.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["ticket_id", "app_account_id"])
        for t in w.t["sup_tickets"].values():
            wr.writerow([t["id"], t["_account_id"] or ""])
    # why people really left vs. what each system recorded - handy for checking your own text analysis
    surveys = {x["account_id"]: x for x in w.t["app_exit_surveys"].values()}
    billing = {a["billing_customer_id"]: a["account_id"] for a in w.t["app_accounts"].values() if a["billing_customer_id"]}
    cancel = {billing[s["customer_id"]]: s["cancellation_details"] for s in w.t["bill_subscriptions"].values()
              if s["cancellation_details"] and s["customer_id"] in billing}
    with open(out_dir / "churn_reasons.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["app_account_id", "true_reason", "app_churn_reason", "survey_reason_code", "survey_text", "billing_cancel_reason"])
        for a in w.t["app_accounts"].values():
            if a["_true_churn_reason"]:
                sv, cd = surveys.get(a["account_id"]), cancel.get(a["account_id"])
                wr.writerow([a["account_id"], a["_true_churn_reason"], a["churn_reason"] or "",
                             sv["reason_code"] if sv else "", (sv["free_text"] or "") if sv else "", cd["reason"] if cd else ""])
    # records that should be filtered out before analysis
    with open(out_dir / "junk_records.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["kind", "record_id"])
        for sh in w.shops.values():
            if sh["internal"] and sh["account_id"]:
                wr.writerow(["internal_test_account", sh["account_id"]])
        for a in w.t["app_accounts"].values():
            if a["status"] == "merged":
                wr.writerow(["merged_duplicate_account", a["account_id"]])
        for e in w.t["mkt_events"].values():
            if e["_bot"]:
                wr.writerow(["bot_event", e["event_id"]])
