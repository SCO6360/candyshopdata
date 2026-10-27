import copy
from datetime import date

import pytest

from candyshop.sim import engine

SEED = 7
AS_OF = date(2025, 12, 31)   # short history keeps the suite fast


@pytest.fixture(scope="session")
def world():
    return engine.build_world(SEED, AS_OF)


@pytest.fixture(scope="session")
def full_world():
    """The default-size history (to 2026-10-25) for tests about late-dated behaviour like schema drift."""
    return engine.build_world(SEED)


@pytest.fixture()
def fresh_world():
    """A private copy that tests may mutate (e.g. by calling grow)."""
    return engine.build_world(SEED, AS_OF)
