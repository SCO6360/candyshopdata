"""Writers: turn the simulated world into the five source formats."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .. import config as C
from ..sim.world import World
from .. import connections
from . import app_db, billing, crm, marketing, support, truth


def write_all(w: World) -> dict[str, dict]:
    """Write every source to data/. Returns per-source row counts."""
    out = {
        "app_db (PostgreSQL seed.sql)": app_db.write_seed(w, C.APP_DIR),
        "crm (CSV)": {"contacts": crm.write(w, C.CRM_DIR)},
        "marketing (JSON)": {"events": marketing.write(w, C.MKT_DIR)},
        "billing (Parquet)": billing.write(w, C.BILLING_DIR),
        "support (REST API JSON)": support.write(w, C.SUPPORT_DIR),
    }
    truth.write(w, C.TRUTH_DIR)
    # freshness stamp that the live services report, so you can tell whether they have caught up
    meta = {"as_of": w.clock.isoformat(), "messiness": w.messiness, "seed": w.seed,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rows": {k: sum(v.values()) for k, v in out.items()}}
    (C.DATA_DIR / "_meta.json").write_text(json.dumps(meta, indent=1))
    connections.write()
    return out
