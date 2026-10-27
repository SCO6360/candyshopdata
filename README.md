# candyshopdata

A generator of **fake but realistic data for a made-up SaaS company**, built to be ingested by something else.

**SweetReach** is an app that helps candy shops find local buyers (school fundraisers, weddings, offices...) and sell
more candy. This tool simulates SweetReach's business day by day and writes what its five systems would have recorded.
The five sources deliberately disagree with each other, so combining them is a real-world exercise.

| # | Source | Format | How your next step picks it up |
|---|--------|--------|--------------------------------|
| 1 | Application database | **PostgreSQL** (live) | read-only login to schema `app` |
| 2 | Third-party CRM export | **CSV** | file in `data/crm/`, or a download link |
| 3 | Marketing events | **JSON** | REST API, pulled with `since` + page tokens |
| 4 | Billing | **Parquet** | file downloads with ETags (skip unchanged files) |
| 5 | Support desk | **REST API** | cursor pagination, `updated_since` |

Roughly 1,000 rows each for the main tables (CRM contacts, marketing events, tickets, users, orders), uneven on purpose.
The data is **generated, not committed**: `data/` is gitignored.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

candy init                 # simulate the business and write all five sources to data/
candy status               # row counts, data date, history
candy grow                 # move the business forward ~a month: ~10% more rows in every source
candy init --force --messiness 3   # rebuild from scratch, nightmare mode
```

Everything uses a seed, so `candy init` always produces the same data. Use `--seed N` for a different world.

### Live sources, and how to pick the data up

You don't maintain the data; you read it from the sources. After `candy init` the services are up (`candy up` uses Docker;
without Docker see below), and **`candy connections`** prints every URL, credential and endpoint (it also writes
`data/_connections.json`):

```
PostgreSQL (read-only)  postgresql://candy_reader:candy_reader@localhost:5432/sweetreach      schema app
Support REST API        http://localhost:8800/api/v2                 Authorization: Bearer demo-token
Marketing REST API      http://localhost:8800/api/v1/marketing
Billing Parquet         http://localhost:8800/api/v1/billing/exports/<name>.parquet
CRM CSV                 http://localhost:8800/api/v1/crm/export      (or data/crm/crm_contacts_export.csv)
Interactive docs        http://localhost:8800/docs
```

```bash
candy up              # Docker: PostgreSQL + the HTTP server, then loads the data (restart: unless-stopped)
candy down            # stop them (-v also deletes the database volume)
candy status          # are the database and the APIs up to date with the files?
```

Without Docker, point `APP_DB_URL` at any PostgreSQL you run (the loading user needs to be able to create a role), then:

```bash
candy load-db         # create/refresh schema "app" (upsert); --reset drops and rebuilds it
candy serve-api       # one HTTP server for the support, marketing, billing and CRM endpoints
```

**`candy grow` updates every live source for you.** It rewrites the files (which the HTTP server re-reads on each request),
upserts the new and changed rows into a running PostgreSQL (nothing is dropped, so a consumer connected to the database is
undisturbed), checks that the database row counts match the dataset, and confirms the API is serving the new data date.
`candy init --force` does a full reset of the database. Use `--no-sync` to only write files.

The same stability applies to failures: the support/marketing/billing endpoints can return transient 500/502/503 and
overlapping pages (set `CANDY_API_FLAKY=0` to disable), so a consumer needs retries and de-duplication, as with real vendors.

`docker-compose.yml` / `candy up` has not been exercised on a machine with Docker yet. Everything else (`psql -f seed.sql`,
`load-db`, sync, the read-only role, all endpoints and a consumer picking up all five sources before and after `grow`) was
tested against PostgreSQL 18.

## Growing the data

`candy grow` does not append random rows. It resumes the same simulation: new prospects arrive, trials convert, invoices
renew, cards fail, shops churn and file tickets. Existing records keep their identity; their *status* moves on (a lead is
won, a ticket is solved, a subscription is canceled). Each run adds at least 10% more rows (`--percent N` to change) and
prints what's new and what happened to each live source. The simulation state lives in `data/_state/` (gitignored).

## Free text

Plenty of it, written by templates keyed to the situation, with typing noise:

* `app.exit_surveys.free_text` - why a shop cancelled. The dropdown `reason_code` often disagrees with the text.
* `app.nps_responses.comment`, `app.leads.notes`
* CRM `Call Notes` and `Notes` (including "LOST: ..." reasons), marketing form `message` / webinar `question`
* billing `cancellation_details.comment`
* support ticket `description` and every comment in the thread

## The real-world challenge

There is no shared key. Each system identifies a shop differently: app `account_id` (int), billing `cus_...`, CRM
`Record ID`, support organization id, marketing email / anonymous id. Links exist but are incomplete, and the sources
conflict. `--messiness` (0 clean, 1 light, **2 default**, 3 nightmare) scales the mess:

* **Identity:** duplicate CRM people, missing/stale `App Account ID`, personal vs. business emails, shared inboxes
  (`info@`), typos, curly apostrophes, `CA` vs `California`, `St.`/`Saint`, name variants (`LLC`, ALL CAPS)
* **Conflicting facts:** shops rebrand or move (CRM keeps the old name/city), multi-location chains share one owner,
  email and domain, a duplicate sign-up is later merged away
* **Junk:** internal `TEST` shops (100% discount in billing), bot traffic in the web events, duplicate and retried webhook
  events, events delivered late and out of order
* **Drift over time:** the marketing payload changes shape on 2026-03-01 (`contact` -> `person`, `utm` -> `attribution`),
  the CRM renames stages ("SQL" -> "Sales Qualified Lead") after 2026-05-01 and gains a column on 2026-03-01
* **Formats and clocks:** CRM in US Eastern local time with no zone, marketing mixing ISO strings and epoch milliseconds,
  billing in UTC cents, ids as ints vs. strings
* **Money:** partial refunds, taxed vs. untaxed invoices, discount codes that expire after N cycles
* **API behaviour:** bearer auth, cursor pagination, rate-limit 429s, transient 500/502/503, pages that overlap
  (`CANDY_API_FLAKY=0` turns the flakiness off)

### The answer key

`data/_truth/` is **not a data source**; it's how you'd check your own work. `crosswalk.csv` maps every shop to its ids in
every system; `churn_reasons.csv` has the real reason each shop left next to what each system recorded;
`junk_records.csv` lists test accounts, merged duplicates and bot events; plus event-to-shop and ticket-to-account maps.

## Is it realistic?

Behaviour is simulated, not random, so analyses find real structure: referrals convert best, while cold
outreach and paid social convert worst; demand and lead types follow the calendar (Halloween, Valentine's, back-to-school fundraisers, December
corporate gifts); low-engagement shops churn more and their activity drops *before* they cancel; failed payments precede
billing tickets and involuntary churn; three platform incidents produce visible ticket spikes.

## Layout

```
candyshop/
  connections.py  the connection details printed by `candy connections`
  vocab.py        cities, products, lead types, seasons, ticket and survey text
  sim/            the day-by-day simulation (crm, marketing, app, billing, support, engine)
  emit/           writers: Postgres seed + loader, CSV, JSON, Parquet, support JSON, answer key
  api/            the hosted sources (FastAPI): support, marketing, billing exports, CRM export
  cli.py          the `candy` command
tests/            pytest suite  (python -m pytest)
```
