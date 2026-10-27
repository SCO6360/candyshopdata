"""Paths and global constants for the SweetReach candy-shop dataset."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CANDY_DATA_DIR", ROOT / "data"))
STATE_PATH = DATA_DIR / "_state" / "world.pkl.gz"
WAREHOUSE_PATH = Path(os.environ.get("CANDY_WAREHOUSE", ROOT / "warehouse" / "candyshop.duckdb"))

# Where each source lands on disk
APP_DIR = DATA_DIR / "app_db"
CRM_DIR = DATA_DIR / "crm"
MKT_DIR = DATA_DIR / "marketing"
BILLING_DIR = DATA_DIR / "billing"
SUPPORT_DIR = DATA_DIR / "support"
TRUTH_DIR = DATA_DIR / "_truth"

DEFAULT_SEED = 2026
CRM_START = date(2025, 4, 1)        # sales started prospecting candy shops
APP_LAUNCH = date(2025, 6, 2)       # SweetReach public launch
INITIAL_AS_OF = date(2026, 10, 25)  # "today" for the first build

DEFAULT_DB_URL = os.environ.get(
    "APP_DB_URL", "postgresql://sweetreach:sweetreach@localhost:5432/sweetreach"
)
DEFAULT_SUPPORT_URL = os.environ.get("SUPPORT_API_URL", "http://localhost:8800")
SUPPORT_API_TOKEN = os.environ.get("SUPPORT_API_TOKEN", "demo-token")
