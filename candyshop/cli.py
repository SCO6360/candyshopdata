"""`candy` - build, grow and inspect the SweetReach multi-source dataset."""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date

from . import config as C
from .emit import write_all
from .sim import engine
from .sim.world import SOURCE_OF, STATIC_TABLES, World


def _load() -> World:
    if not C.STATE_PATH.exists():
        sys.exit("No dataset yet. Run `candy init` first.")
    return World.load(C.STATE_PATH)


def _src_table(rows: list[tuple]) -> str:
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  " + "  ".join(str(c).ljust(widths[i]) if i == 0 else str(c).rjust(widths[i]) for i, c in enumerate(r)) for r in rows)


def _sync_live(w: World, *, reset: bool, enabled: bool = True) -> None:
    """Push the new data to every live source that is running, and say what happened to each."""
    import json
    import urllib.request
    from .emit import app_db

    print("\nLive sources:")
    print("  CRM CSV, marketing JSON, billing Parquet, support JSON : files rewritten in", C.DATA_DIR)
    if not enabled:
        print("  PostgreSQL : skipped (--no-sync). Run `candy load-db` when ready.")
    else:
        try:
            counts = app_db.sync_postgres(w, C.DEFAULT_DB_URL, reset=reset)
            print(f"  PostgreSQL : {'reloaded' if reset else 'synced'} -> {C.DEFAULT_DB_URL.split('@')[-1]}  "
                  f"({counts['accounts']} accounts, {counts['orders']} orders, {counts['leads']} leads)")
            expected = {t: len(w.t[wt]) for t, (wt, _c) in app_db.APP_TABLES.items()}
            off = {t: (counts[t], n) for t, n in expected.items() if counts[t] != n}
            if off:   # e.g. leftovers from a different dataset in the same database
                print("  !! row counts differ from the dataset: " + ", ".join(f"{t} db={a} expected={b}" for t, (a, b) in off.items())
                      + "\n     run `candy load-db --reset` to rebuild the database from scratch")
        except Exception as e:   # not running / not reachable is normal on a laptop
            first = str(e).strip().splitlines()[0][:90] if str(e).strip() else type(e).__name__
            print(f"  PostgreSQL : not updated ({first}). Start it with `candy up`, then `candy load-db`.")
    try:
        with urllib.request.urlopen(f"{C.DEFAULT_SUPPORT_URL}/health", timeout=2) as r:
            info = json.load(r)
        ok = info.get("data_as_of") == w.clock.isoformat()
        print(f"  REST APIs  : {C.DEFAULT_SUPPORT_URL} serving data as of {info.get('data_as_of')}  "
              f"{'(up to date)' if ok else '(STALE - is it reading a different data folder?)'}")
    except Exception:
        print(f"  REST APIs  : not running at {C.DEFAULT_SUPPORT_URL} (they pick up new data automatically when started)")


def cmd_init(args) -> None:
    if C.STATE_PATH.exists() and not args.force:
        sys.exit("A dataset already exists. Use `candy init --force` to rebuild it from scratch (or `candy grow` to add more).")
    if args.force:
        for d in (C.APP_DIR, C.CRM_DIR, C.MKT_DIR, C.BILLING_DIR, C.SUPPORT_DIR, C.TRUTH_DIR, C.STATE_PATH.parent):
            shutil.rmtree(d, ignore_errors=True)
    as_of = date.fromisoformat(args.as_of) if args.as_of else C.INITIAL_AS_OF
    print(f"Simulating SweetReach from {C.CRM_START} to {as_of} (seed {args.seed}, messiness {args.messiness}) ...")
    w = engine.build_world(args.seed, as_of, args.messiness)
    counts = write_all(w)
    w.save(C.STATE_PATH)
    _print_counts(w, counts)
    _sync_live(w, reset=True, enabled=not args.no_sync)
    print(f"\nDone. Files are in {C.DATA_DIR}. Next: `candy connections` shows how to pick each source up; `candy grow` adds more.")


def _print_counts(w: World, counts: dict) -> None:
    print(f"\nData as of {w.clock}:")
    for src, tables in counts.items():
        total = sum(tables.values())
        detail = ", ".join(f"{k}={v}" for k, v in tables.items())
        print(f"  {src:<30} {total:>6} rows   ({detail})")


def cmd_grow(args) -> None:
    w = _load()
    before_as_of = w.clock
    entry = engine.grow(w, args.percent)
    counts = write_all(w)
    w.save(C.STATE_PATH)
    delta = entry["delta"]
    print(f"Advanced the business {entry['days_advanced']} days: {before_as_of} -> {w.clock}  "
          f"(+{sum(v for k, v in delta.items() if k not in STATIC_TABLES)} rows, "
          f"{entry['total']} total, requested +{args.percent:g}%)\n")
    rows = [("source", "rows added", "rows now")]
    now = engine.source_counts(entry["counts"])
    for src, tables in SOURCE_OF.items():
        rows.append((src, "+" + str(sum(delta[t] for t in tables)), now[src]))
    print(_src_table(rows))
    _print_highlights(w, before_as_of)
    _sync_live(w, reset=False, enabled=not args.no_sync)


def _print_highlights(w: World, since: date) -> None:
    from datetime import datetime
    cut = datetime(since.year, since.month, since.day) + __import__("datetime").timedelta(days=1)
    t = w.t
    new = lambda table, col: [r for r in t[table].values() if r[col] >= cut]  # noqa: E731
    new_accts = new("app_accounts", "created_at")
    churned = [a for a in t["app_accounts"].values() if a["churned_at"] and a["churned_at"] >= cut]
    paid = [i for i in new("bill_invoices", "created_at") if i["status"] == "paid"]
    print("\nWhat's new:")
    print(f"  {len(new('crm_contacts', 'created_at'))} CRM contacts, {len(new_accts)} new app accounts "
          f"({sum(a['signup_source'] == 'self_serve' for a in new_accts)} self-serve), {len(churned)} churned")
    print(f"  {len(new('app_leads', 'created_at'))} leads, {len(new('app_campaigns', 'created_at'))} campaigns, "
          f"{len(new('app_orders', 'ordered_at'))} orders (${sum(o['total'] for o in new('app_orders', 'ordered_at')):,.0f})")
    print(f"  {len(paid)} paid invoices (${sum(i['total_cents'] for i in paid) / 100:,.0f}), "
          f"{len(new('sup_tickets', 'created_at'))} support tickets, {len(new('mkt_events', 'occurred_at'))} marketing events")


def cmd_status(args) -> None:
    w = _load()
    print(f"SweetReach dataset  |  seed {w.seed}  |  data as of {w.clock}  |  state: {C.STATE_PATH}")
    rows = [("table", "rows")]
    for name, n in w.counts().items():
        rows.append((name, n))
    print(_src_table(rows))
    print("\nBy source:")
    print(_src_table([("source", "rows")] + [(k, v) for k, v in engine.source_counts(w.counts()).items()]))
    from .emit import app_db
    import json, urllib.request
    print("\nLive sources (files are as of %s):" % w.clock)
    db = app_db.db_as_of(C.DEFAULT_DB_URL)
    print(f"  PostgreSQL : {'not reachable / no data' if db is None else 'as of ' + db + ('  (up to date)' if db == w.clock.isoformat() else '  (STALE - run `candy load-db`)')}")
    try:
        with urllib.request.urlopen(f"{C.DEFAULT_SUPPORT_URL}/health", timeout=2) as r:
            api = json.load(r).get("data_as_of")
        print(f"  REST APIs  : as of {api}{'  (up to date)' if api == w.clock.isoformat() else '  (STALE)'}")
    except Exception:
        print(f"  REST APIs  : not running at {C.DEFAULT_SUPPORT_URL}")
    print("\nHistory:")
    for h in w.history:
        extra = f"  +{h['days_advanced']}d" if h["action"] == "grow" else ""
        print(f"  {h['action']:<5} as_of={h['as_of']}  total={h['total']}{extra}")


def cmd_load_db(args) -> None:
    from .emit import app_db
    w = _load()
    print(f"{'Rebuilding' if args.reset else 'Syncing'} app tables in {args.url.split('@')[-1]} ...")
    counts = app_db.sync_postgres(w, args.url, reset=args.reset)
    for t, n in counts.items():
        print(f"  app.{t:<14} {n:>6} rows")


def cmd_connections(args) -> None:
    import json
    from . import connections
    info = connections.write()
    print(json.dumps(info, indent=2) if args.json else connections.render(info))


def cmd_serve_api(args) -> None:
    import uvicorn
    uvicorn.run("candyshop.api.server:app", host=args.host, port=args.port, reload=False)


def _compose(*args: str) -> int:
    import subprocess
    if shutil.which("docker") is None:
        sys.exit("Docker is not installed. Install Docker, or run PostgreSQL yourself and use `candy load-db` + `candy serve-api`.")
    return subprocess.call(["docker", "compose", *args], cwd=C.ROOT)


def cmd_up(args) -> None:
    import time
    if not C.STATE_PATH.exists():
        print("No data yet - running `candy init` first.")
        cmd_init(argparse.Namespace(force=False, seed=C.DEFAULT_SEED, as_of=None, messiness=args.messiness, no_sync=True))
    if _compose("up", "-d", "--build", "--wait") != 0:
        sys.exit("docker compose failed to start the services.")
    print("Loading the latest data into PostgreSQL ...")
    cmd_load_db(argparse.Namespace(url=C.DEFAULT_DB_URL, reset=False))
    from . import connections
    print("\nReady.\n" + connections.render(connections.write()))


def cmd_down(args) -> None:
    sys.exit(_compose("down", *(["-v"] if args.volumes else [])))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="candy", description="Build, grow and inspect the SweetReach candy-shop dataset.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="simulate the business and write all five sources")
    s.add_argument("--seed", type=int, default=C.DEFAULT_SEED)
    s.add_argument("--as-of", help="end date for the initial history (default %s)" % C.INITIAL_AS_OF)
    s.add_argument("--messiness", type=int, choices=[0, 1, 2, 3], default=2,
                   help="how much real-world mess to inject: 0 clean, 1 light, 2 realistic (default), 3 nightmare")
    s.add_argument("--force", action="store_true", help="delete existing data and rebuild")
    s.add_argument("--no-sync", action="store_true", help="only write files; do not touch a running PostgreSQL")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("grow", help="move the business forward until the dataset has ~10%% more rows")
    s.add_argument("--percent", type=float, default=10.0, help="minimum growth in total rows (default 10)")
    s.add_argument("--no-sync", action="store_true", help="only write files; do not touch a running PostgreSQL")
    s.set_defaults(fn=cmd_grow)

    s = sub.add_parser("status", help="row counts, data date and history")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("load-db", help="create/refresh the app tables in PostgreSQL (upsert; --reset drops and rebuilds)")
    s.add_argument("--url", default=C.DEFAULT_DB_URL)
    s.add_argument("--reset", action="store_true", help="drop schema `app` and reload everything")
    s.set_defaults(fn=cmd_load_db)

    s = sub.add_parser("up", help="start PostgreSQL + the support API in Docker and load the data (runs `init` if needed)")
    s.add_argument("--messiness", type=int, choices=[0, 1, 2, 3], default=2)
    s.set_defaults(fn=cmd_up)

    s = sub.add_parser("down", help="stop the Docker services")
    s.add_argument("-v", "--volumes", action="store_true", help="also delete the PostgreSQL volume")
    s.set_defaults(fn=cmd_down)

    s = sub.add_parser("connections", help="show how to connect to each source (URLs, credentials, endpoints)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_connections)

    s = sub.add_parser("serve-api", help="serve the support-desk REST API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8800)
    s.set_defaults(fn=cmd_serve_api)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
