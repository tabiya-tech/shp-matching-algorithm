#!/usr/bin/env python3
"""Explain Mongo query plan for jobs retrieval (active + location OR)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from pymongo import MongoClient


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_user(users_json: Path, idx: int) -> Dict[str, Any]:
    with open(users_json, encoding="utf-8") as f:
        raw = json.load(f)
    u = raw[idx]
    return {k: v for k, v in u.items() if not str(k).startswith("_")}


def _stage_names(plan: Any, out: list[str]) -> None:
    if isinstance(plan, dict):
        st = plan.get("stage")
        if st:
            out.append(str(st))
        for v in plan.values():
            _stage_names(v, out)
    elif isinstance(plan, list):
        for it in plan:
            _stage_names(it, out)


def main() -> int:
    backend = _backend_root()
    sys.path.insert(0, str(backend))
    load_dotenv(backend / ".env")

    ap = argparse.ArgumentParser()
    ap.add_argument("--users-json", type=Path, default=backend / "tests" / "test_users.json")
    ap.add_argument("--user-index", type=int, default=0)
    ap.add_argument("--limit", type=int, default=10000)
    args = ap.parse_args()

    from app.config import MONGO_JOBS_COLLECTION
    from app.database import build_mongo_filter_active_and_location

    user = _load_user(args.users_json, args.user_index)
    filt = build_mongo_filter_active_and_location([user])
    if filt is None:
        print("No filter built")
        return 1

    url = os.getenv("MONGO_URL")
    db_name = os.getenv("MONGO_DB_NAME")
    if not url or not db_name:
        print("MONGO_URL / MONGO_DB_NAME are required in .env")
        return 1

    client = MongoClient(url, serverSelectionTimeoutMS=15000)
    coll = client[db_name][MONGO_JOBS_COLLECTION]

    find_cmd: Dict[str, Any] = {
        "find": MONGO_JOBS_COLLECTION,
        "filter": filt,
        "sort": {"_id": -1},
    }
    if args.limit > 0:
        find_cmd["limit"] = args.limit

    exp = client[db_name].command("explain", find_cmd, verbosity="executionStats")
    stats = exp.get("executionStats", {})
    qp = exp.get("queryPlanner", {})
    winning = qp.get("winningPlan", {})
    rejected = qp.get("rejectedPlans", [])

    stages: list[str] = []
    _stage_names(winning, stages)
    stage_str = " -> ".join(stages[:10]) if stages else "(unknown)"

    out = {
        "collection": MONGO_JOBS_COLLECTION,
        "user_id": user.get("user_id"),
        "city": user.get("city"),
        "province": user.get("province"),
        "filter_has_or": "$or" in json.dumps(filt),
        "limit": args.limit,
        "planner_namespace": qp.get("namespace"),
        "winning_plan_stages": stage_str,
        "n_rejected_plans": len(rejected),
        "execution_time_ms": stats.get("executionTimeMillis"),
        "n_returned": stats.get("nReturned"),
        "total_keys_examined": stats.get("totalKeysExamined"),
        "total_docs_examined": stats.get("totalDocsExamined"),
    }
    print(json.dumps(out, indent=2))
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
