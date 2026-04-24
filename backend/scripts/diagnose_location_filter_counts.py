#!/usr/bin/env python3
"""Compare Mongo prefilter count vs strict in-memory _job_matches_user_location (one user)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


async def main() -> None:
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    from dotenv import load_dotenv

    load_dotenv(backend / ".env")
    os.environ["JOBS_RETRIEVAL_FILTER"] = "0"

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--users-json",
        type=Path,
        default=backend / "tests" / "test_users.json",
    )
    ap.add_argument("--user-index", type=int, default=0)
    args = ap.parse_args()

    from app.config import MONGO_JOBS_COLLECTION
    from app.database import (
        RANKED_JOBS_ACTIVE_FILTER,
        build_mongo_filter_active_and_location,
        db,
        get_all_jobs,
    )
    from app.services.matching_service import _job_matches_user_location

    with open(args.users_json, encoding="utf-8") as f:
        raw = json.load(f)
    u = raw[args.user_index]
    user = {k: v for k, v in u.items() if not str(k).startswith("_")}

    col = db[MONGO_JOBS_COLLECTION]
    n_all = await col.count_documents({})
    n_active = await col.count_documents(RANKED_JOBS_ACTIVE_FILTER)
    flt = build_mongo_filter_active_and_location([user])
    n_mongo_prefilter = await col.count_documents(flt)

    jobs = await get_all_jobs()
    n_py = sum(1 for j in jobs if _job_matches_user_location(j, user))
    n_py_fail = len(jobs) - n_py

    print("--- Location filter diagnosis ---")
    print(f"User index {args.user_index}: city={user.get('city')!r} province={user.get('province')!r}")
    print(f"Mongo total documents (any is_active):     {n_all}")
    print(f"Mongo active (is_active true):             {n_active}")
    print(f"Mongo count with active+location OR:       {n_mongo_prefilter}")
    print(f"Loaded jobs (get_all_jobs, active only):   {len(jobs)}")
    print(f"In-memory _job_matches_user_location pass: {n_py}")
    print(f"In-memory location filter FAIL (strict):   {n_py_fail}")
    gap = n_mongo_prefilter - n_py
    print(
        f"\nMongo prefilter minus Python-pass:         {gap} "
        f"({'Mongo OR is looser than strict filter' if gap > 0 else 'same' if gap == 0 else 'check logic'})"
    )


if __name__ == "__main__":
    asyncio.run(main())
