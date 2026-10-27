"""The simulated world: tables, entities, RNG helpers and an event scheduler.

The whole dataset is produced by simulating SweetReach one day at a time. Every row in every
source is a by-product of that single simulation, which is why the five sources agree with
each other (a failed card payment in billing really does precede a billing ticket in support
and a past_due account in the app database).

State is persisted (pickle) so `candy grow` can resume the same world and add more history.
"""
from __future__ import annotations

import gzip
import heapq
import math
import pickle
import random
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from faker import Faker

from ..config import CRM_START

# Emitted tables (name -> primary key). Order matters only for display.
TABLES = {
    "app_plans": "plan_id", "app_products": "product_id", "app_accounts": "account_id", "app_users": "user_id",
    "app_leads": "lead_id", "app_campaigns": "campaign_id", "app_orders": "order_id",
    "app_order_items": "order_item_id", "app_exit_surveys": "survey_id", "app_nps": "response_id",
    "crm_contacts": "record_id",
    "mkt_events": "event_id",
    "bill_customers": "customer_id", "bill_subscriptions": "subscription_id", "bill_invoices": "invoice_id",
    "bill_payments": "payment_id",
    "sup_tickets": "id", "sup_comments": "id", "sup_users": "id", "sup_orgs": "id",
}
SOURCE_OF = {
    "app": [t for t in TABLES if t.startswith("app_")],
    "crm": ["crm_contacts"],
    "marketing": ["mkt_events"],
    "billing": [t for t in TABLES if t.startswith("bill_")],
    "support": [t for t in TABLES if t.startswith("sup_")],
}
STATIC_TABLES = {"app_plans", "app_products"}

HANDLERS: dict[str, Callable[..., None]] = {}


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


class World:
    def __init__(self, seed: int, messiness: int = 2):
        self.seed = seed
        self.messiness = messiness   # 0 = clean ... 3 = nightmare
        self.rng = random.Random(seed)
        self.start: date = CRM_START
        self.clock: date = CRM_START - timedelta(days=1)  # last fully simulated day
        self.t: dict[str, dict[Any, dict]] = {name: {} for name in TABLES}
        self.shops: dict[str, dict] = {}            # ground truth entity per candy shop
        self.ids: dict[str, int] = defaultdict(int)
        self.heap: list = []
        self._n = 0
        self.mkt_campaigns: dict[str, dict] = {}
        self.incidents: dict[date, tuple[str, str]] = {}
        self.history: list[dict] = []               # one entry per init/grow
        self.index: dict[str, Any] = defaultdict(dict)  # misc lookup tables (email -> user etc.)
        self.fake = Faker("en_US")

    # ------------------------------------------------------------------ persistence
    def __getstate__(self):
        s = self.__dict__.copy()
        s["fake"] = None
        s["index"] = dict(self.index)
        return s

    def __setstate__(self, s):
        self.__dict__.update(s)
        idx = defaultdict(dict)
        idx.update(self.__dict__.get("index", {}))
        self.index = idx
        self.fake = Faker("en_US")

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wb") as fh:
            pickle.dump(self, fh, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def load(path: Path) -> "World":
        with gzip.open(path, "rb") as fh:
            return pickle.load(fh)

    # ------------------------------------------------------------------ randomness
    def chance(self, p: float) -> bool:
        return self.rng.random() < p

    def mess(self, p: float) -> bool:
        """True with probability p scaled by the messiness dial (0, x0.5, x1, x2)."""
        return self.rng.random() < min(1.0, p * (0.0, 0.5, 1.0, 2.0)[self.messiness])

    def pick(self, items, weights=None):
        if weights is None:
            return self.rng.choice(items)
        return self.rng.choices(items, weights=weights)[0]

    def pick_pairs(self, pairs):
        """pairs: [(value, weight), ...]"""
        return self.rng.choices([p[0] for p in pairs], weights=[p[1] for p in pairs])[0]

    def poisson(self, lam: float) -> int:
        if lam <= 0:
            return 0
        if lam > 30:
            return max(0, int(round(self.rng.gauss(lam, math.sqrt(lam)))))
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= limit:
                return k
            k += 1

    def lognorm(self, median: float, sigma: float) -> float:
        return median * math.exp(self.rng.gauss(0, sigma))

    def phone(self) -> str:
        return f"({self.rng.randint(201, 989)}) {self.rng.randint(200, 999)}-{self.rng.randint(0, 9999):04d}"

    def uuid(self) -> str:
        return str(uuid.UUID(int=self.rng.getrandbits(128), version=4))

    def token(self, prefix: str, n: int = 14) -> str:
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return prefix + "".join(self.rng.choice(alphabet) for _ in range(n))

    def seed_day(self, d: date) -> None:
        self.fake.seed_instance(self.seed * 1_000_003 + d.toordinal())

    def moment(self, d: date, start_h: float = 7.5, end_h: float = 19.5) -> datetime:
        secs = self.rng.uniform(start_h * 3600, end_h * 3600)
        return datetime(d.year, d.month, d.day) + timedelta(seconds=secs)

    def nid(self, name: str, first: int) -> int:
        self.ids[name] += 1
        return first + self.ids[name] - 1

    # ------------------------------------------------------------------ scheduler
    def schedule(self, due: datetime, kind: str, **payload) -> None:
        heapq.heappush(self.heap, (due, self._n, kind, payload))
        self._n += 1

    def run_due(self, until: datetime) -> None:
        while self.heap and self.heap[0][0] <= until:
            due, _n, kind, payload = heapq.heappop(self.heap)
            HANDLERS[kind](self, due, **payload)

    # ------------------------------------------------------------------ counts
    def counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.t.items()}

    def total_rows(self) -> int:
        return sum(len(r) for n, r in self.t.items() if n not in STATIC_TABLES)

    def add(self, table: str, row: dict) -> dict:
        self.t[table][row[TABLES[table]]] = row
        return row
