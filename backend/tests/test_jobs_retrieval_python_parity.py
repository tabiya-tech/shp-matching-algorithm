"""
Mongo retrieval filter on vs off: after applying _job_matches_user_location,
the number of passing jobs must be the same (Mongo is a superset of the same Python rule).

Requires Mongo (see backend/.env). Skips if ping fails.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import os

import pytest
from dotenv import load_dotenv
from pymongo import MongoClient

_BACKEND = Path(__file__).resolve().parents[1]
_TEST_USERS = _BACKEND / "tests" / "test_users.json"


def _first_test_user() -> dict:
    with open(_TEST_USERS, encoding="utf-8") as f:
        raw = json.load(f)[0]
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


@pytest.fixture(scope="module")
def mongo_available() -> bool:
    """Sync ping only — asyncio.run here would close the loop and break Motor in tests."""
    load_dotenv(_BACKEND / ".env")
    url = os.getenv("MONGO_URL")
    if not url:
        return False
    try:
        c = MongoClient(url, serverSelectionTimeoutMS=5000)
        c.admin.command("ping")
        c.close()
    except Exception:
        return False
    return True


def test_python_location_pass_count_same_with_mongo_filter_on_or_off(
    monkeypatch: pytest.MonkeyPatch, mongo_available: bool
) -> None:
    if not mongo_available:
        pytest.skip("Mongo not available")

    user = _first_test_user()
    import app.database as dbmod

    async def load_both_in_one_loop() -> tuple[int, int, int, int]:
        """One event loop: Motor breaks if asyncio.run is called twice in a row."""
        from app.database import get_all_jobs_with_timing
        from app.services.matching_service import _job_matches_user_location

        monkeypatch.setattr(dbmod, "JOBS_RETRIEVAL_FILTER", True)
        jobs_on, _ = await get_all_jobs_with_timing(users=[user])
        n_py_on = sum(1 for j in jobs_on if _job_matches_user_location(j, user))
        n_loaded_on = len(jobs_on)

        monkeypatch.setattr(dbmod, "JOBS_RETRIEVAL_FILTER", False)
        jobs_off, _ = await get_all_jobs_with_timing(users=[user])
        n_py_off = sum(1 for j in jobs_off if _job_matches_user_location(j, user))
        n_loaded_off = len(jobs_off)

        return n_py_on, n_loaded_on, n_py_off, n_loaded_off

    n_py_on, n_loaded_on, n_py_off, n_loaded_off = asyncio.run(load_both_in_one_loop())

    assert n_py_on == n_py_off, (
        "Count after _job_matches_user_location must match whether Mongo prefilter is on; "
        f"on={n_py_on} (loaded {n_loaded_on}), off={n_py_off} (loaded {n_loaded_off}). "
        "If this fails, the Mongo OR is stricter than Python for some documents."
    )
    assert n_loaded_on <= n_loaded_off, (
        "With Mongo filter on, we should load at most as many jobs as all active; "
        f"got loaded_on={n_loaded_on} loaded_off={n_loaded_off}"
    )
