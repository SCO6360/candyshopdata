"""Source 2 - CSV export from the third-party CRM that sales uses to prospect candy shops.

Real CRM exports are messy, so this one is too: mixed state formats ("CA" vs "California"), assorted
phone formats, company-name variants ("... LLC"), duplicate people, upper-case emails, missing
domains and a blank `App Account ID` for some customers whose sync failed.

All mess is derived from the record id (not the global RNG), so re-exporting after `candy grow`
leaves existing rows byte-for-byte stable.
"""
from __future__ import annotations

import csv
import random
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import vocab as V
from ..sim.world import World

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

COLUMNS = [
    "Record ID", "First Name", "Last Name", "Email", "Phone Number", "Job Title", "Company Name", "Company Domain Name",
    "City", "State/Region", "Lead Source", "Original Source Campaign", "Lifecycle Stage", "Lead Status", "Contact Owner",
    "Create Date", "Last Modified Date", "Last Contacted", "Number of Sales Activities", "Deal Amount", "Close Date",
    "App Account ID", "Do Not Email", "Notes", "Call Notes", "Engagement Score",
]


def _ts(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.replace(tzinfo=UTC).astimezone(ET).strftime("%m/%d/%Y %H:%M")


def _phone(r: random.Random, phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    return r.choice([phone, f"{digits[:3]}-{digits[3:6]}-{digits[6:]}", f"{digits[:3]}.{digits[3:6]}.{digits[6:]}",
                     f"+1{digits}", digits])


CURLY = str.maketrans({"'": "\u2019"})
DRIFT_DATE = datetime(2026, 5, 1)          # after this date the CRM vendor renamed stages and statuses
SCORE_DATE = datetime(2026, 3, 1)          # the "Engagement Score" column was only populated from here on
LONG_STAGE = {"MQL": "Marketing Qualified Lead", "SQL": "Sales Qualified Lead"}


def _company(r: random.Random, shop: dict, m: float) -> str:
    name, legal = shop["crm_name"], shop["crm_legal"]
    x = r.random()
    if x < 0.55:
        out = name
    elif x < 0.88:
        out = legal
    elif x < 0.93:
        out = name.upper() if m > 0 else name
    elif x < 0.97:
        out = name.replace("&", "and").replace("Co.", "Company")
    else:
        out = name.replace("The ", "")
    if r.random() < 0.30 * m:
        out = out.translate(CURLY)
    if r.random() < 0.03 * m and len(out) > 6:      # a typo from whoever keyed it in
        i = r.randrange(1, len(out) - 2)
        out = out[:i] + out[i + 1] + out[i] + out[i + 2:]
    return out


def row_for(w: World, c: dict) -> list:
    m = (0.0, 0.5, 1.0, 2.0)[w.messiness]
    shop = w.shops[c["_shop_id"]]
    r = random.Random(c["record_id"])
    email = c["email"]
    x = r.random()
    if x < 0.05 * m:
        email = email.capitalize()
    elif x < 0.07 * m:
        email = email + " "
    elif x < 0.09 * m:
        email = email.upper()
    elif x < 0.10 * m and "@" in email:       # fat-fingered domain
        email = email.replace(".com", ".con") if ".com" in email else email.replace("gmail", "gmial")
    if shop["domain"] and r.random() < 0.08 * m:   # sales entered the shop's shared inbox instead of the person
        email = f"{r.choice(['info', 'hello', 'orders', 'sales'])}@{shop['domain']}"
    state = shop["state"]
    x = r.random()
    if x < 0.15 * m:
        state = V.STATE_NAMES.get(state, state)
    elif x < 0.20 * m:
        state = state.lower()
    domain = shop["domain"] or ""
    if r.random() < 0.10 * m:
        domain = ""
    elif domain and r.random() < 0.08 * m:
        domain = "www." + domain
    city = shop["crm_city"]
    if r.random() < 0.04 * m:
        city = city.lower()
    elif city.startswith("St. ") and r.random() < 0.3 * m:
        city = "Saint " + city[4:]
    stage, status = c["lifecycle_stage"], c["lead_status"]
    if w.messiness > 0 and c["last_modified"] >= DRIFT_DATE:    # vendor changed its picklists mid-stream
        stage = LONG_STAGE.get(stage, stage)
        status = status.upper().replace(" ", "_")
    score = ""
    if c["created_at"] >= SCORE_DATE:
        score = int(min(100, max(1, (r.gauss(55, 20)))))
    return [
        c["record_id"], c["first_name"], c["last_name"], email, _phone(r, c["phone"]), c["job_title"], _company(r, shop, m), domain,
        city, state, c["lead_source"], c["original_source_campaign"], stage, status, c["owner"],
        _ts(c["created_at"]), _ts(c["last_modified"]), _ts(c["last_contacted"]), c["sales_activities"],
        "" if c["deal_amount"] is None else f"{c['deal_amount']:.2f}",
        c["close_date"].strftime("%m/%d/%Y") if c["close_date"] else "",
        c["app_account_id"] if c["app_account_id"] else "", "Yes" if c["do_not_email"] else "No", c["notes"],
        " | ".join(c["call_notes"]), score,
    ]


def write(w: World, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    contacts = sorted(w.t["crm_contacts"].values(), key=lambda c: c["record_id"])
    with open(out_dir / "crm_contacts_export.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        wr.writerow(COLUMNS)
        for c in contacts:
            wr.writerow(row_for(w, c))
    return len(contacts)
