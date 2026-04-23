#!/usr/bin/env python3
"""
One-off migration: read an existing ``RankedJobs``-shaped collection and write copies
to a *new* collection in the same database with two extra fields (no change to the source):

1) ``onet_work_activities`` — O*NET work activities with ``WA_Importance`` / ``WA_Level``
   filled from the same taxonomy logic as ``app.database._enrich_work_activities`` (BWS / û path).
2) ``skill_groups_origin_uuids`` — parent group IDs for job essential+optional skills via the same
   skill→group hierarchy as ``SkillScorer`` (p̂ / feasibility path).

The source collection is **never** modified. Re-run is safe: upsert by ``job_id`` (or ``_id`` fallback).

Environment: ``MONGO_URL``, ``MONGO_DB_NAME`` (or ``.env`` in ``backend/``).

Example (from ``backend/``)::

  python scripts/enrich_ranked_jobs_to_new_collection.py \\
    --source RankedJobs \\
    --dest RankedJobsEnriched \\
    --dry-run

  python scripts/enrich_ranked_jobs_to_new_collection.py \\
    --source RankedJobs \\
    --dest RankedJobsEnriched
"""

from __future__ import annotations

import argparse
import copy
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Path: run from repository ``backend/`` (or any cwd if backend is on PYTHONPATH)
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from dotenv import load_dotenv

load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

from pymongo import MongoClient, ReplaceOne
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.database import _enrich_work_activities, _load_wa_lookup
from app.services.skill_score import SkillScorer

logger = logging.getLogger("enrich_ranked_jobs")


def _enrich_one(
    raw: Dict[str, Any],
    scorer: SkillScorer,
) -> Tuple[Dict[str, Any], int, int]:
    """
    Return (document_to_write, n_onet_rows, n_skill_group_ids).
    """
    out = copy.deepcopy(raw)

    wa_items = (out.get("work_activity") or {}).get("items", []) or []
    classified = out.get("classified_occupations") or []
    if wa_items:
        onet = _enrich_work_activities(wa_items, classified)
    else:
        onet = []

    lcs = out.get("llm_classified_skills") or {}
    ess = [
        s.get("tabiya_skill_id")
        for s in lcs.get("essential", [])
        if isinstance(s, dict) and s.get("tabiya_skill_id")
    ]
    opt = [
        s.get("tabiya_skill_id")
        for s in lcs.get("optional", [])
        if isinstance(s, dict) and s.get("tabiya_skill_id")
    ]
    sids: set = set()
    for s in ess + opt:
        sids.add(scorer._resolve_id(str(s)))
    group_ids = sorted(scorer._derive_groups(sids))

    out["onet_work_activities"] = onet
    out["skill_groups_origin_uuids"] = group_ids
    out["enrichment"] = {
        "at": datetime.now(timezone.utc),
        "version": 1,
        "source_script": "enrich_ranked_jobs_to_new_collection.py",
    }
    return out, len(onet), len(group_ids)


def _client() -> Tuple[MongoClient, str]:
    url = (os.getenv("MONGO_URL") or "").strip()
    dbn = (os.getenv("MONGO_DB_NAME") or os.getenv("MONGO_DB") or "").strip()
    if not url:
        raise SystemExit("MONGO_URL is not set")
    if not dbn:
        raise SystemExit("MONGO_DB_NAME is not set")
    return MongoClient(url), dbn


def run(
    source: str,
    dest: str,
    *,
    dry_run: bool,
    limit: Optional[int],
    filter_active: bool,
    batch_size: int,
) -> None:
    _load_wa_lookup()  # warm taxonomy once (also logs "Built WA lookup...")
    logger.info("Loading SkillScorer (embeddings + hierarchy) — this can take a minute on first run.")
    scorer = SkillScorer()

    client, db_name = _client()
    db = client[db_name]
    src: Collection = db[source]
    dst: Collection = db[dest]

    q: Dict[str, Any] = {}
    if filter_active:
        q["is_active"] = True

    total = src.count_documents(q)
    to_process = min(total, limit) if limit is not None else total
    logger.info("Source=%s dest=%s filter=%s documents≈%s (limit=%s)", source, dest, q, to_process, limit)

    cursor = src.find(q)
    n_ok = 0
    n_err = 0
    bulk: list[ReplaceOne] = []

    for i, doc in enumerate(cursor):
        if limit is not None and i >= limit:
            break
        try:
            enriched, n_wa, n_g = _enrich_one(doc, scorer)
            jid = enriched.get("job_id")
            if dry_run and i < 3:
                logger.info(
                    "dry sample job_id=%s onet_wa_rows=%d skill_groups=%d",
                    jid,
                    n_wa,
                    n_g,
                )
            if dry_run:
                n_ok += 1
                continue

            # Full document replace/insert so the destination always has a complete copy + enrichment
            eid = doc.get("_id")
            if eid is None:
                n_err += 1
                logger.error("Document without _id, skipped job_id=%s", jid)
                continue
            bulk.append(ReplaceOne({"_id": eid}, enriched, upsert=True))
            n_ok += 1
            if len(bulk) >= batch_size:
                dst.bulk_write(bulk, ordered=False)
                bulk.clear()
        except Exception as e:
            n_err += 1
            logger.exception("Failed job_id=%s: %s", doc.get("job_id"), e)

    if not dry_run and bulk:
        dst.bulk_write(bulk, ordered=False)

    logger.info("Done. written_ok=%d errors=%s dry_run=%s", n_ok, n_err, dry_run)
    if not dry_run:
        logger.info("Consider: db.%s.createIndex({ job_id: 1 }, { unique: true })", dest)
    client.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default="RankedJobs", help="Source collection (read-only)")
    p.add_argument(
        "--dest",
        default="RankedJobsEnriched",
        help="Destination collection in the same database (upsert; created if missing)",
    )
    p.add_argument("--dry-run", action="store_true", help="Parse and log a few samples; do not write")
    p.add_argument("--limit", type=int, default=None, help="Max documents to process (for tests)")
    p.add_argument(
        "--filter-active",
        action="store_true",
        help="Only process documents with is_active == true (default: all documents in source)",
    )
    p.add_argument("--batch-size", type=int, default=200, help="Bulk write batch size")
    args = p.parse_args()

    try:
        run(
            args.source,
            args.dest,
            dry_run=bool(args.dry_run),
            limit=args.limit,
            filter_active=bool(args.filter_active),
            batch_size=max(1, int(args.batch_size)),
        )
    except (PyMongoError, SystemExit) as e:
        if isinstance(e, SystemExit):
            raise
        logger.exception("Mongo error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
