"""Day-by-day simulation loop. `build_world` creates the initial history; `grow` continues it."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .. import vocab as V
from ..config import APP_LAUNCH, INITIAL_AS_OF
from . import app, billing, crm, marketing, support  # noqa: F401  (imports register the event handlers)
from .world import SOURCE_OF, World


def new_world(seed: int, messiness: int = 2) -> World:
    w = World(seed, messiness)
    for d, area, title in V.INCIDENTS:
        w.incidents[d] = (area, title)
    app.seed_static(w)
    return w


def step_day(w: World, d: date) -> None:
    w.seed_day(d)
    crm.arrivals(w, d)
    if d >= APP_LAUNCH and w.mess(0.012):
        app.spawn_test_account(w, d)
    marketing.daily(w, d)
    app.daily(w, d)
    support.daily(w, d)
    w.run_due(datetime(d.year, d.month, d.day) + timedelta(days=1) - timedelta(microseconds=1))
    w.clock = d


def advance_to(w: World, end: date) -> int:
    n = 0
    while w.clock < end:
        step_day(w, w.clock + timedelta(days=1))
        n += 1
    return n


def snapshot(w: World) -> dict:
    counts = w.counts()
    return {"as_of": w.clock.isoformat(), "counts": counts, "total": w.total_rows()}


def build_world(seed: int, as_of: date = INITIAL_AS_OF, messiness: int = 2) -> World:
    w = new_world(seed, messiness)
    advance_to(w, as_of)
    w.history.append({"action": "init", "messiness": messiness, **snapshot(w)})
    return w


def grow(w: World, percent: float = 10.0, max_days: int = 400) -> dict:
    """Advance the simulation until the dataset has grown by at least `percent` percent (row count)."""
    before = snapshot(w)
    target = before["total"] * (1 + percent / 100)
    days = 0
    while w.total_rows() < target and days < max_days:
        step_day(w, w.clock + timedelta(days=1))
        days += 1
    after = snapshot(w)
    entry = {"action": "grow", "percent_requested": percent, "days_advanced": days, **after,
             "delta": {k: after["counts"][k] - before["counts"][k] for k in after["counts"]}}
    w.history.append(entry)
    return entry


def source_counts(counts: dict[str, int]) -> dict[str, int]:
    return {src: sum(counts[t] for t in tables) for src, tables in SOURCE_OF.items()}
