"""
Compare multiplicative vs additive scoring on the same jobs for each test user.
Outputs: backend/tests/algo_comparison.csv

Runs both scoring modes per user, collects up to 20 results per mode,
then merges them side-by-side keyed by job UUID so every row shows
both algorithms' view of the same (user, job) pair.
"""
import asyncio
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import app.services.matching_service as ms_mod
from app.database import get_all_jobs
from app.services.matching_service import _match_items

TOP_K = 20


def _extract(result: dict) -> dict:
    """Pull numeric fields from a formatted opportunity result."""
    sb = result.get("score_breakdown", {})
    sc = sb.get("skill_components", {})
    ms = result.get("matched_skills", {})
    return {
        "rank": result.get("rank"),
        "final_score": result.get("final_score"),
        "skill_utility": sb.get("total_skill_utility"),
        "ess": sc.get("ess"),
        "opt": sc.get("opt"),
        "loc": sc.get("loc"),
        "pref_score": sb.get("preference_score"),
        "demand_score": sb.get("demand_score", ""),
        "demand_label": sb.get("demand_label", ""),
        "essential_matches": len(ms.get("essential_skill_matches", [])),
        "optional_matches": len(ms.get("optional_exact_matches", [])),
    }


async def run_comparison():
    with open(os.path.join(os.path.dirname(__file__), "test_users.json")) as f:
        users = json.load(f)

    jobs = await get_all_jobs()
    print(f"Loaded {len(jobs)} jobs")

    rows = []

    for user in users:
        uid = user["user_id"]
        print(f"Processing {uid} …")

        ms_mod.SCORING_MODE = "multiplicative"
        mult_results = _match_items(user, jobs, item_type="opportunity", top_k=TOP_K)

        ms_mod.SCORING_MODE = "additive"
        add_results = _match_items(user, jobs, item_type="opportunity", top_k=TOP_K)

        mult_map = {r["uuid"]: r for r in mult_results}
        add_map = {r["uuid"]: r for r in add_results}
        all_uuids = list(dict.fromkeys(
            [r["uuid"] for r in mult_results] + [r["uuid"] for r in add_results]
        ))

        for job_uuid in all_uuids:
            m_raw = mult_map.get(job_uuid)
            a_raw = add_map.get(job_uuid)

            any_raw = m_raw or a_raw
            title = any_raw.get("opportunity_title", "")
            location = any_raw.get("location", "")

            m = _extract(m_raw) if m_raw else {}
            a = _extract(a_raw) if a_raw else {}

            row = {
                "user_id": uid,
                "job_uuid": job_uuid,
                "job_title": title,
                "job_location": location,
            }

            for prefix, d in [("mult", m), ("add", a)]:
                row[f"{prefix}_rank"] = d.get("rank", "")
                row[f"{prefix}_final_score"] = d.get("final_score", "")
                row[f"{prefix}_skill_utility"] = d.get("skill_utility", "")
                row[f"{prefix}_ess"] = d.get("ess", "")
                row[f"{prefix}_opt"] = d.get("opt", "")
                row[f"{prefix}_loc"] = d.get("loc", "")
                row[f"{prefix}_pref_score"] = d.get("pref_score", "")
                row[f"{prefix}_essential_matches"] = d.get("essential_matches", "")
                row[f"{prefix}_optional_matches"] = d.get("optional_matches", "")

            if prefix == "add":
                row["add_demand_score"] = a.get("demand_score", "")
                row["add_demand_label"] = a.get("demand_label", "")

            if m and a:
                row["rank_delta"] = a["rank"] - m["rank"]
                row["score_delta_mult_minus_add"] = round(m["final_score"] - a["final_score"], 4)
            else:
                row["rank_delta"] = ""
                row["score_delta_mult_minus_add"] = ""

            rows.append(row)

    ms_mod.SCORING_MODE = "multiplicative"

    out_path = os.path.join(os.path.dirname(__file__), "algo_comparison.csv")
    fieldnames = list(rows[0].keys()) if rows else []
    with open(out_path, "w", newline="") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {out_path}")

    both = [r for r in rows if r["mult_rank"] != "" and r["add_rank"] != ""]
    mult_only = [r for r in rows if r["mult_rank"] != "" and r["add_rank"] == ""]
    add_only = [r for r in rows if r["mult_rank"] == "" and r["add_rank"] != ""]
    print(f"  Jobs in both top-{TOP_K}: {len(both)}")
    print(f"  Jobs only in multiplicative top-{TOP_K}: {len(mult_only)}")
    print(f"  Jobs only in additive top-{TOP_K}: {len(add_only)}")

    if both:
        rank_changes = [r for r in both if r["rank_delta"] != 0]
        avg_score_delta = sum(abs(float(r["score_delta_mult_minus_add"])) for r in both) / len(both)
        print(f"  Rank changes: {len(rank_changes)}/{len(both)}")
        print(f"  Avg |score delta|: {avg_score_delta:.4f}")


if __name__ == "__main__":
    asyncio.run(run_comparison())
