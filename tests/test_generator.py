import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta

import pyarrow.parquet as pq
import pytest

from candyshop.emit import app_db, billing, crm, marketing, support, truth
from candyshop.sim import engine
from candyshop.sim.world import STATIC_TABLES, TABLES
from conftest import AS_OF, SEED


def test_headline_tables_are_populated(world):
    c = world.counts()
    for table in TABLES:
        assert c[table] > 0, table
    # the five sources should be the same order of magnitude but deliberately uneven
    by_source = engine.source_counts(c)
    assert min(by_source.values()) > 100 and len(set(by_source.values())) == 5


def test_deterministic_for_a_seed(world):
    again = engine.build_world(SEED, AS_OF)
    assert again.counts() == world.counts()
    assert [c["email"] for c in again.t["crm_contacts"].values()] == [c["email"] for c in world.t["crm_contacts"].values()]


def test_different_seed_differs(world):
    other = engine.build_world(SEED + 1, AS_OF)
    assert other.counts() != world.counts()


def test_no_row_is_dated_after_the_data_date(world):
    cutoff = datetime(AS_OF.year, AS_OF.month, AS_OF.day) + timedelta(days=1)
    for name, rows in world.t.items():
        for row in rows.values():
            for key, val in row.items():
                if isinstance(val, datetime) and not key.startswith("_") and key not in ("trial_ends_at", "current_period_end", "period_end"):
                    assert val < cutoff, (name, key, val)


def test_referential_integrity(world):
    t = world.t
    accounts, users, orders = t["app_accounts"], t["app_users"], t["app_orders"]
    assert all(u["account_id"] in accounts for u in users.values())
    assert all(l["account_id"] in accounts and (l["assigned_user_id"] in users or l["assigned_user_id"] is None) for l in t["app_leads"].values())
    assert all(o["account_id"] in accounts for o in orders.values())
    assert all(o["lead_id"] is None or o["lead_id"] in t["app_leads"] for o in orders.values())
    assert all(o["campaign_id"] is None or o["campaign_id"] in t["app_campaigns"] for o in orders.values())
    assert all(i["order_id"] in orders and i["product_id"] in t["app_products"] for i in t["app_order_items"].values())
    assert all(s["customer_id"] in t["bill_customers"] for s in t["bill_subscriptions"].values())
    assert all(i["customer_id"] in t["bill_customers"] and i["subscription_id"] in t["bill_subscriptions"] for i in t["bill_invoices"].values())
    assert all(p["invoice_id"] in t["bill_invoices"] for p in t["bill_payments"].values())
    assert all(c["ticket_id"] in t["sup_tickets"] and c["author_id"] in t["sup_users"] for c in t["sup_comments"].values())
    assert all(tk["requester_id"] in t["sup_users"] and tk["assignee_id"] in t["sup_users"] for tk in t["sup_tickets"].values())
    assert all(tk["organization_id"] is None or tk["organization_id"] in t["sup_orgs"] for tk in t["sup_tickets"].values())


def test_order_totals_add_up(world):
    items = {}
    for i in world.t["app_order_items"].values():
        items[i["order_id"]] = items.get(i["order_id"], 0) + i["quantity"] * i["unit_price"]
    for o in world.t["app_orders"].values():
        assert o["subtotal"] == pytest.approx(items[o["order_id"]], abs=0.01)
        assert o["total"] == pytest.approx(o["subtotal"] - o["discount"], abs=0.01)


def test_cross_source_links_exist_but_are_imperfect(world):
    t = world.t
    paying = [a for a in t["app_accounts"].values() if a["billing_customer_id"]]
    assert paying and all(a["billing_customer_id"] in t["bill_customers"] for a in paying)
    crm_ids = [c["app_account_id"] for c in t["crm_contacts"].values() if c["app_account_id"]]
    assert crm_ids and all(i in t["app_accounts"] for i in crm_ids)
    customers = [a for a in t["app_accounts"].values() if a["signup_source"] == "sales_assisted"]
    linked = {c["app_account_id"] for c in t["crm_contacts"].values() if c["app_account_id"]}
    assert 0 < len(linked) < len(customers)                    # some CRM->app links are missing on purpose
    assert any(c["_dup"] for c in t["crm_contacts"].values())  # duplicate people exist
    assert any(c["metadata_app_account_id"] is None for c in t["bill_customers"].values())


def test_failed_payments_lead_to_billing_activity(world):
    failed = [p for p in world.t["bill_payments"].values() if p["status"] == "failed"]
    assert failed
    assert {p["failure_code"] for p in failed} <= {"card_declined", "expired_card", "insufficient_funds", "processing_error"}
    assert any("payment_failed" in t["tags"] for t in world.t["sup_tickets"].values())


def test_grow_adds_at_least_ten_percent_and_keeps_history(fresh_world):
    w = fresh_world
    before_total, before_clock = w.total_rows(), w.clock
    before_orders = {k: v["total"] for k, v in w.t["app_orders"].items()}
    before_emails = {k: v["email"] for k, v in w.t["crm_contacts"].items()}
    entry = engine.grow(w, 10)
    assert w.clock > before_clock and entry["days_advanced"] > 0
    assert w.total_rows() >= before_total * 1.10
    assert w.total_rows() < before_total * 1.20, "a single grow step should not overshoot wildly"
    assert all(w.t["app_orders"][k]["total"] == v for k, v in before_orders.items())
    assert all(w.t["crm_contacts"][k]["email"] == v for k, v in before_emails.items())
    assert entry["delta"]["crm_contacts"] >= 0 and sum(entry["delta"].values()) > 0
    assert [h["action"] for h in w.history] == ["init", "grow"]


def test_grow_is_repeatable(fresh_world):
    a, b = fresh_world, engine.build_world(SEED, AS_OF)
    engine.grow(a, 10)
    engine.grow(b, 10)
    assert a.counts() == b.counts()


def test_state_survives_save_and_load(world, tmp_path):
    from candyshop.sim.world import World
    world.save(tmp_path / "w.pkl.gz")
    loaded = World.load(tmp_path / "w.pkl.gz")
    assert loaded.counts() == world.counts() and loaded.clock == world.clock
    engine.grow(loaded, 5)   # a reloaded world can keep simulating
    assert loaded.total_rows() > world.total_rows()


# ------------------------------------------------------------------ writers
def test_all_five_sources_are_written(world, tmp_path):
    app_counts = app_db.write_seed(world, tmp_path / "app")
    assert app_counts["accounts"] == len(world.t["app_accounts"])
    seed = (tmp_path / "app" / "seed.sql").read_text()
    for table in app_db.APP_TABLES:
        assert f"COPY app.{table} (" in seed
    assert crm.write(world, tmp_path / "crm") == len(world.t["crm_contacts"])
    # the export also contains duplicate deliveries and retries, so it holds at least as many events as the simulation
    assert marketing.write(world, tmp_path / "mkt") >= len(world.t["mkt_events"])
    bc = billing.write(world, tmp_path / "bill")
    assert bc["invoices"] == len(world.t["bill_invoices"])
    sc = support.write(world, tmp_path / "sup")
    assert sc["tickets"] == len(world.t["sup_tickets"])
    truth.write(world, tmp_path / "truth")
    assert (tmp_path / "truth" / "crosswalk.csv").exists()


def test_crm_csv_is_messy_but_stable(world, tmp_path):
    crm.write(world, tmp_path / "a")
    crm.write(world, tmp_path / "b")
    a = (tmp_path / "a" / "crm_contacts_export.csv").read_bytes()
    assert a == (tmp_path / "b" / "crm_contacts_export.csv").read_bytes()   # re-export is byte-stable
    rows = list(csv.DictReader(open(tmp_path / "a" / "crm_contacts_export.csv", encoding="utf-8")))
    states = {r["State/Region"] for r in rows}
    assert any(len(s) > 2 for s in states) and any(len(s) == 2 for s in states)   # "California" and "CA"
    assert any(r["Email"] != r["Email"].strip().lower() for r in rows)
    assert any(r["App Account ID"] == "" and r["Lifecycle Stage"] == "Customer" for r in rows)
    assert re.fullmatch(r"\d\d/\d\d/\d{4} \d\d:\d\d", rows[0]["Create Date"])


def test_marketing_json_mixes_two_systems(world, tmp_path):
    marketing.write(world, tmp_path)
    doc = json.loads((tmp_path / "marketing_events.json").read_text())
    assert doc["export_meta"]["event_count"] == len(doc["events"]) and doc["campaigns"]
    ma = [e for e in doc["events"] if e["source_system"] == "marketing_automation"]
    wa = [e for e in doc["events"] if e["source_system"] == "web_analytics"]
    assert ma and wa
    assert all("occurred_at" in e and "ts" not in e for e in ma)
    assert all(isinstance(e["ts"], int) and "occurred_at" not in e for e in wa)
    assert any("anonymousId" in e and "contact" not in e for e in wa)


def test_billing_parquet_types(world, tmp_path):
    billing.write(world, tmp_path)
    inv = pq.read_table(tmp_path / "invoices.parquet")
    assert str(inv.schema.field("total_cents").type) == "int64"
    assert str(inv.schema.field("created_at").type).startswith("timestamp[us, tz=UTC]")
    assert inv.num_rows == len(world.t["bill_invoices"])
    assert "app_account_id" in [f.name for f in inv.schema.field("metadata").type]


def test_app_schema_matches_writer_columns():
    sql = app_db.schema_sql()
    for table, (_wt, cols) in app_db.APP_TABLES.items():
        body = re.search(rf"CREATE TABLE {table} \((.*?)\n\);", sql, re.S).group(1)
        declared = [m.group(1) for m in re.finditer(r"^\s{4}(\w+)\s+\w", body, re.M)]
        assert declared == cols, table


def test_copy_text_escaping():
    assert app_db._cell(None) == r"\N"
    assert app_db._cell("a\tb\nc\\d") == r"a\tb\nc\\d"
    assert app_db._cell({"k": [1, 2]}) == '{"k":[1,2]}'
    assert app_db._cell(True) == "t"


# ------------------------------------------------------------------ support API
@pytest.fixture()
def api_client(world, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from candyshop.api import billing_api, crm_api, marketing_api, server, support_api
    support.write(world, tmp_path)
    marketing.write(world, tmp_path / "mkt")
    billing.write(world, tmp_path / "bill")
    crm.write(world, tmp_path / "crm")
    monkeypatch.setattr(marketing_api, "MKT_DIR", tmp_path / "mkt")
    monkeypatch.setattr(billing_api, "BILLING_DIR", tmp_path / "bill")
    monkeypatch.setattr(crm_api, "CRM_DIR", tmp_path / "crm")
    marketing_api._cache.clear()
    monkeypatch.setattr(support_api, "SUPPORT_DIR", tmp_path)
    monkeypatch.setattr(support_api, "SUPPORT_API_TOKEN", "t0ken")
    monkeypatch.setattr(support_api, "FLAKY", False)
    support_api._cache.clear()
    support_api._hits.clear()
    return TestClient(server.app, headers={"Authorization": "Bearer t0ken"})


def test_api_requires_a_token(api_client):
    assert api_client.get("/health").status_code == 200
    assert api_client.get("/api/v2/tickets", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_api_pagination_walks_every_ticket(api_client, world):
    seen, cursor = [], None
    while True:
        r = api_client.get("/api/v2/tickets", params={"per_page": 50, **({"cursor": cursor} if cursor else {})})
        body = r.json()
        seen += [t["id"] for t in body["tickets"]]
        if not body["meta"]["has_more"]:
            break
        cursor = body["meta"]["after_cursor"]
    assert seen == sorted(world.t["sup_tickets"])


def test_api_filters_and_lookups(api_client, world):
    some = next(iter(world.t["sup_tickets"].values()))
    assert api_client.get(f"/api/v2/tickets/{some['id']}").json()["ticket"]["subject"] == some["subject"]
    assert api_client.get("/api/v2/tickets/999999").status_code == 404
    comments = api_client.get(f"/api/v2/tickets/{some['id']}/comments").json()["comments"]
    assert comments and all(c["ticket_id"] == some["id"] for c in comments)
    solved = api_client.get("/api/v2/tickets", params={"status": "closed", "per_page": 100}).json()["tickets"]
    assert solved and all(t["status"] == "closed" for t in solved)
    future = api_client.get("/api/v2/tickets", params={"updated_since": "2999-01-01T00:00:00Z"}).json()
    assert future["tickets"] == [] and future["meta"]["count"] == 0
    assert api_client.get("/api/v2/tickets/search", params={"query": "spam"}).json()["meta"]["count"] >= 0


def test_api_rate_limit_returns_429(api_client, monkeypatch):
    from candyshop.api import support_api
    monkeypatch.setattr(support_api, "RATE_LIMIT", 3)
    codes = [api_client.get("/api/v2/groups").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429


# ------------------------------------------------------------------ CLI end to end
def test_cli_init_grow_status(tmp_path):
    env = {"CANDY_DATA_DIR": str(tmp_path / "data"), "PATH": "/usr/bin:/bin"}
    run = lambda *a: subprocess.run([sys.executable, "-m", "candyshop.cli", *a], env=env, capture_output=True, text=True)  # noqa: E731
    r = run("status")
    assert r.returncode != 0 and "candy init" in (r.stdout + r.stderr)
    r = run("init", "--as-of", "2025-12-31", "--seed", "3")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "data" / "crm" / "crm_contacts_export.csv").exists()
    assert run("init").returncode != 0                      # refuses to overwrite without --force
    r = run("grow")
    assert r.returncode == 0 and "What's new" in r.stdout, r.stderr
    assert "grow" in run("status").stdout
    assert run("init", "--force", "--as-of", "2025-12-31", "--seed", "3").returncode == 0


# ------------------------------------------------------------------ free text + messiness
def test_free_text_exists_in_every_source(full_world):
    t = full_world.t
    assert any(s["free_text"] for s in t["app_exit_surveys"].values())
    assert any(n["comment"] for n in t["app_nps"].values())
    assert sum(1 for l in t["app_leads"].values() if l["notes"]) > 100
    assert any(c["call_notes"] for c in t["crm_contacts"].values())
    assert any("message" in e["properties"] for e in t["mkt_events"].values())
    assert any(s["cancellation_details"] and s["cancellation_details"]["comment"] for s in t["bill_subscriptions"].values())
    assert len(t["sup_comments"]) > len(t["sup_tickets"])


def test_exit_survey_text_matches_the_true_reason_but_the_dropdown_may_not(world):
    from candyshop import vocab as V
    surveys = [s for s in world.t["app_exit_surveys"].values() if s["free_text"]]
    assert surveys
    wrong_code = 0
    for s in surveys:
        assert s["_true_reason"] in V.EXIT_TEXT
        if s["reason_code"] != V.EXIT_CODES[s["_true_reason"]]:
            wrong_code += 1
    assert 0 < wrong_code < len(surveys)          # dropdown is unreliable, but not useless


def test_messiness_zero_is_clean_and_three_is_worse():
    clean = engine.build_world(SEED, AS_OF, 0)
    messy = engine.build_world(SEED, AS_OF, 3)

    def census(w):
        return dict(
            merged=sum(a["status"] == "merged" for a in w.t["app_accounts"].values()),
            internal=sum(s["internal"] for s in w.shops.values()),
            chains=len({s["chain_id"] for s in w.shops.values() if s["chain_id"]}),
            bots=sum(e["_bot"] for e in w.t["mkt_events"].values()),
            refunds=sum(p["status"] == "refunded" for p in w.t["bill_payments"].values()),
            wrong_codes=sum(1 for a in w.t["app_accounts"].values() if a["_true_churn_reason"] and a["churn_reason"] != a["_true_churn_reason"]),
        )
    c, m = census(clean), census(messy)
    assert all(v == 0 for v in c.values()), c
    assert m["internal"] > 0 and m["chains"] > 0 and m["merged"] >= 0 and m["refunds"] > 0


def test_mess_shows_up_in_the_files(tmp_path):
    w = engine.build_world(SEED, messiness=3)
    marketing.write(w, tmp_path / "m")
    crm.write(w, tmp_path / "c")
    events = json.loads((tmp_path / "m" / "marketing_events.json").read_text())["events"]
    ids = [e["event_id"] for e in events]
    assert len(ids) != len(set(ids)), "expected duplicate deliveries"
    assert any(e.get("schema") == 2 and "person" in e for e in events), "expected v2 payloads after the drift date"
    assert any("contact" in e for e in events), "expected v1 payloads before the drift date"
    rows = list(csv.DictReader(open(tmp_path / "c" / "crm_contacts_export.csv", encoding="utf-8")))
    assert any(r["Lifecycle Stage"] == "Sales Qualified Lead" for r in rows) or any(r["Lifecycle Stage"] == "SQL" for r in rows)
    assert any(r["Engagement Score"] for r in rows) and any(not r["Engagement Score"] for r in rows)


def test_chains_share_identity_fields(world):
    from collections import defaultdict
    chains = defaultdict(list)
    for s in world.shops.values():
        if s["chain_id"]:
            chains[s["chain_id"]].append(s)
    assert chains
    for members in chains.values():
        assert len(members) >= 2 and len({m["owner_email"] for m in members}) == 1 and len({m["domain"] for m in members}) == 1


def test_stale_crm_copy_after_rebrand(full_world):
    changed = [s for s in full_world.shops.values() if s["crm_name"] != s["name"]]
    assert changed, "expected at least one shop whose CRM name is stale"


def test_truth_files_written(world, tmp_path):
    truth.write(world, tmp_path)
    for name in ("crosswalk.csv", "churn_reasons.csv", "junk_records.csv", "marketing_event_shop.csv", "ticket_account.csv"):
        assert (tmp_path / name).exists()
    rows = list(csv.DictReader(open(tmp_path / "churn_reasons.csv", encoding="utf-8")))
    assert rows and {"true_reason", "survey_text", "app_churn_reason"} <= set(rows[0])


def test_api_can_be_flaky_and_overlap_pages(api_client, tmp_path, monkeypatch):
    from candyshop.api import support_api
    monkeypatch.setattr(support_api, "FLAKY", True)
    (tmp_path / "_api_config.json").write_text(json.dumps({"error_rate": 1.0, "overlap_rate": 0.0}))
    assert api_client.get("/api/v2/groups").status_code in (500, 502, 503)
    (tmp_path / "_api_config.json").write_text(json.dumps({"error_rate": 0.0, "overlap_rate": 1.0}))
    first = api_client.get("/api/v2/tickets", params={"per_page": 5}).json()
    second = api_client.get("/api/v2/tickets", params={"per_page": 5, "cursor": first["meta"]["after_cursor"]}).json()
    assert second["tickets"][0]["id"] == first["tickets"][-1]["id"]       # the overlap trap


# ------------------------------------------------------------------ the other hosted sources
def test_marketing_api_pages_through_every_event(api_client, tmp_path):
    exported = json.loads((tmp_path / "mkt" / "marketing_events.json").read_text())["events"]
    got, token = [], None
    while True:
        d = api_client.get("/api/v1/marketing/events", params={"per_page": 200, **({"page_token": token} if token else {})}).json()
        got += d["events"]
        token = d["next_page_token"]
        if not token:
            break
    assert len(got) == len(exported) == d["total"]
    assert api_client.get("/api/v1/marketing/events", params={"since": "2999-01-01T00:00:00Z"}).json()["events"] == []
    one = api_client.get("/api/v1/marketing/events", params={"event_type": "form_submit", "per_page": 5}).json()["events"]
    assert one and all(e["event_type"] == "form_submit" for e in one)
    assert api_client.get("/api/v1/marketing/campaigns").json()["campaigns"]
    assert api_client.get("/api/v1/marketing/events", params={"page_token": "!!"}).status_code == 400


def test_billing_exports_download_and_etag(api_client, world):
    import io
    listing = api_client.get("/api/v1/billing/exports").json()["exports"]
    assert {e["name"] for e in listing} == {"customers.parquet", "subscriptions.parquet", "invoices.parquet", "payments.parquet"}
    inv = next(e for e in listing if e["name"] == "invoices.parquet")
    assert inv["rows"] == len(world.t["bill_invoices"])
    r = api_client.get("/api/v1/billing/exports/invoices.parquet")
    assert r.status_code == 200 and pq.read_table(io.BytesIO(r.content)).num_rows == inv["rows"]
    assert api_client.get("/api/v1/billing/exports/invoices.parquet", headers={"If-None-Match": r.headers["etag"]}).status_code == 304
    assert api_client.get("/api/v1/billing/exports/..%2Fsecret.parquet").status_code in (400, 404)
    assert api_client.get("/api/v1/billing/exports/nothing.parquet").status_code == 404


def test_crm_export_download(api_client, world):
    r = api_client.get("/api/v1/crm/export")
    assert r.status_code == 200 and r.text.startswith("Record ID,")
    assert api_client.get("/api/v1/crm/export", headers={"If-None-Match": r.headers["etag"]}).status_code == 304


def test_every_hosted_endpoint_requires_the_token(api_client):
    for path in ("/api/v1/marketing/events", "/api/v1/billing/exports", "/api/v1/crm/export", "/api/v2/tickets"):
        assert api_client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401, path


def test_health_reports_data_freshness(api_client, world, tmp_path):
    (tmp_path.parent / "_meta.json").write_text(json.dumps({"as_of": "2026-01-01", "generated_at": "x"}))
    from candyshop.api import support_api
    assert api_client.get("/health").json()["status"] == "ok"


def test_connections_describe_all_sources():
    from candyshop import connections
    info = connections.build()
    assert info["postgres"]["read_only_url"].startswith("postgresql://candy_reader:")
    assert {"postgres", "support_api", "marketing_api", "billing_exports", "crm_export"} <= set(info)
    assert "Billing Parquet" in connections.render(info)


def test_schema_creates_a_read_only_login():
    sql = app_db.schema_sql()
    assert "candy_reader" in sql and "GRANT SELECT ON ALL TABLES IN SCHEMA app" in sql
    assert "GRANT INSERT" not in sql and "GRANT ALL" not in sql
