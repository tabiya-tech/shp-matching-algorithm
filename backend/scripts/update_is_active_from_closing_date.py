#!/usr/bin/env python3
"""
Set `is_active` from `classifier_metadata.closing_date` for the configured jobs collection.

Rules:
  - closing_date < today  -> is_active = False
  - closing_date >= today -> is_active = True
  - missing/unparseable closing_date -> policy-controlled (default: keep unchanged)

Usage:
  cd backend
  python scripts/update_is_active_from_closing_date.py --dry-run
  python scripts/update_is_active_from_closing_date.py --apply
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime
from typing import Optional

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne


def _parse_date(raw: object) -> Optional[date]:
    """Best-effort parser for common closing_date formats."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    # Try ISO first (supports "YYYY-MM-DD" and many datetime variants).
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).date()
    except ValueError:
        pass

    # Common fallback formats seen in mixed datasets.
    patterns = (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
    )
    for p in patterns:
        try:
            return datetime.strptime(s, p).date()
        except ValueError:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist updates to Mongo")
    parser.add_argument("--dry-run", action="store_true", help="Show counts only (default)")
    parser.add_argument(
        "--missing-policy",
        choices=("keep", "active", "inactive"),
        default="keep",
        help="How to handle missing/unparseable closing_date",
    )
    parser.add_argument(
        "--today",
        default=None,
        help="Override today (YYYY-MM-DD) for deterministic runs",
    )
    args = parser.parse_args()

    # Default behavior is dry-run unless --apply is explicitly provided.
    do_apply = bool(args.apply)

    load_dotenv(".env")
    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("MONGO_DB_NAME")
    coll_name = os.getenv("MONGO_JOBS_COLLECTION", "RankedJobsEnriched")
    if not mongo_url or not db_name:
        raise SystemExit("MONGO_URL and MONGO_DB_NAME must be set in backend/.env")

    if args.today:
        today = datetime.strptime(args.today, "%Y-%m-%d").date()
    else:
        today = date.today()

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=15000)
    coll = client[db_name][coll_name]

    total = 0
    parsed = 0
    missing_or_bad = 0
    will_set_true = 0
    will_set_false = 0
    unchanged = 0
    updates = []

    proj = {"_id": 1, "is_active": 1, "classifier_metadata.closing_date": 1}
    for doc in coll.find({}, proj):
        total += 1
        current = bool(doc.get("is_active", False))
        closing_raw = (doc.get("classifier_metadata") or {}).get("closing_date")
        d = _parse_date(closing_raw)

        if d is None:
            missing_or_bad += 1
            if args.missing_policy == "keep":
                target = current
            elif args.missing_policy == "active":
                target = True
            else:
                target = False
        else:
            parsed += 1
            target = d >= today

        if target == current:
            unchanged += 1
            continue

        if target:
            will_set_true += 1
        else:
            will_set_false += 1
        updates.append(UpdateOne({"_id": doc["_id"]}, {"$set": {"is_active": target}}))

    print(f"Collection: {db_name}.{coll_name}")
    print(f"Today: {today.isoformat()}")
    print(f"Total docs scanned: {total}")
    print(f"Parsed closing_date: {parsed}")
    print(f"Missing/unparseable closing_date: {missing_or_bad}")
    print(f"Would set is_active=True: {will_set_true}")
    print(f"Would set is_active=False: {will_set_false}")
    print(f"Unchanged: {unchanged}")

    if not do_apply:
        print("Dry run complete. Re-run with --apply to persist changes.")
        client.close()
        return 0

    if not updates:
        print("No updates to apply.")
        client.close()
        return 0

    res = coll.bulk_write(updates, ordered=False)
    print(
        "Applied updates:",
        f"matched={res.matched_count}",
        f"modified={res.modified_count}",
    )
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

