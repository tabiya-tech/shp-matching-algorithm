#!/usr/bin/env python3
"""
Create recommended indexes on the jobs collection (idempotent).

Improves active-only and active+sort+limit patterns. Regex-heavy location $or
still benefits mainly from fewer docs scanned once is_active is selective.

Usage:
  cd backend && python scripts/ensure_jobs_collection_indexes.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

_BACKEND = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(_BACKEND))
    load_dotenv(_BACKEND / ".env")

    from app.config import MONGO_JOBS_COLLECTION

    url = os.getenv("MONGO_URL")
    db_name = os.getenv("MONGO_DB_NAME")
    if not url or not db_name:
        print("MONGO_URL and MONGO_DB_NAME must be set", file=sys.stderr)
        return 1

    coll = MongoClient(url, serverSelectionTimeoutMS=15000)[db_name][MONGO_JOBS_COLLECTION]

    # Matches get_all_jobs: is_active filter and sort _id desc when retrieval filter is on.
    idx1 = coll.create_index(
        [("is_active", 1), ("_id", -1)],
        name="is_active_1__id_-1",
    )
    print(f"Index is_active_1__id_-1: {idx1}")

    # Optional: common filter branch on classifier_metadata (equality prefix helps less for $regex).
    idx2 = coll.create_index(
        [("classifier_metadata.city", 1)],
        name="classifier_metadata_city_1",
    )
    print(f"Index classifier_metadata.city: {idx2}")

    print("Done (create_index is idempotent if names match).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
