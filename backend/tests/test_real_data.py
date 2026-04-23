"""
Real-data integration test for the matching service.

Uses:
  - RankedJobs collection (classifier_metadata + llm fields on the same document)
    → tabiya_skill_id used directly (matches retrained embedding model)
    → llm_job_attributes for preference-scoring attributes
  - Real user profiles from KenyaJobs_dev.users (mapped_skills + preference_vector)

This script bypasses the HTTP layer and calls matching functions directly.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure backend is on sys.path
backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from pymongo import MongoClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_real_data")

# ---------------------------------------------------------------------------
# 1. DATA LOADING
# ---------------------------------------------------------------------------

def get_mongo_client():
    return MongoClient(os.getenv("MONGO_URL"))


def load_ranked_jobs(client) -> List[Dict[str, Any]]:
    """Transform RankedJobs into the flat dict format for match_single_user / _match_items.

    Uses the same mapping as app.database.build_job_dict_from_ranked.
    """
    from app.config import MONGO_JOBS_COLLECTION
    from app.database import RANKED_JOBS_ACTIVE_FILTER, build_job_dict_from_ranked

    db = client["KenyaJobs"]
    jobs: List[Dict[str, Any]] = []
    for rd in db[MONGO_JOBS_COLLECTION].find(RANKED_JOBS_ACTIVE_FILTER):
        built = build_job_dict_from_ranked(rd)
        if built is not None:
            jobs.append(built)

    return jobs


def load_real_users(client) -> List[Dict[str, Any]]:
    """Load real user profiles from KenyaJobs_dev and other DBs,
    converting mapped_skills into the skills_vector.top_skills format.
    """
    users = []

    sources = [
        ("KenyaJobs_dev", "Kenya Seeker"),
        ("KenyaJobs_dev", "Job Seeker"),
        ("ZambiaJobs_dev", "Hamz Cohan"),
        ("SouthAfricaJobs_dev", "Tabiya Admin"),
        ("SouthAfricaJobs_dev", "Thabo Mbeki"),
    ]

    for db_name, name in sources:
        db = client[db_name]
        doc = db["users"].find_one({"full_name": name})
        if not doc:
            continue

        mapped = doc.get("mapped_skills", [])
        if not mapped:
            continue

        # Build top_skills from mapped_skills
        top_skills = []
        seen_uuids = set()
        for ms in mapped:
            me = ms.get("mapped_entity", {})
            uri = me.get("uri", "")
            esco_uuid = ""
            if "/esco/skill/" in uri:
                esco_uuid = uri.split("/esco/skill/")[-1]

            # Prefer tabiya_skill_id if available, otherwise use ESCO UUID
            origin_uuid = me.get("tabiya_id") or esco_uuid
            if not origin_uuid or origin_uuid in seen_uuids:
                continue
            seen_uuids.add(origin_uuid)

            top_skills.append({
                "preferredLabel": me.get("label", ms.get("original_skill", "")),
                "originUUID": origin_uuid,
                "proficiency": me.get("similarity_score", 0.7),
            })

        # Use existing preference_vector or sensible defaults
        pref = doc.get("preference_vector")
        if not pref:
            pref = {
                "earnings_per_month": 0.5, "task_content": 0.5,
                "physical_demand": 0.3, "work_flexibility": 0.5,
                "social_interaction": 0.3, "career_growth": 0.7,
                "social_meaning": 0.3,
            }

        user = {
            "user_id": str(doc["_id"]),
            "full_name": name,
            "city": doc.get("city") or "Nairobi",
            "province": doc.get("province") or "Nairobi",
            "skills_vector": {"top_skills": top_skills},
            "skill_groups_origin_uuids": [],
            "preference_vector": pref,
            "_source_db": db_name,
        }
        users.append(user)

    return users


# ---------------------------------------------------------------------------
# 2. MATCHING (bypass HTTP, call Python directly)
# ---------------------------------------------------------------------------

from app.services.matching_service import _match_items, scorer_skill
from app.services.skill_gap_analysis import analyze_skill_gaps


def match_user_against_jobs(user: dict, jobs: list) -> dict:
    """Run the full matching pipeline for one user against RankedJobs."""
    t0 = time.time()

    opportunity_recs = _match_items(user, jobs, item_type="opportunity", top_k=10)

    skill_gaps = analyze_skill_gaps(
        user, jobs, scorer_skill.engine, scorer_skill.skill_labels,
        top_k=5, resolve_id=scorer_skill._resolve_id,
    )

    elapsed = time.time() - t0
    return {
        "user_id": user["user_id"],
        "full_name": user["full_name"],
        "city": user["city"],
        "num_skills": len(user["skills_vector"]["top_skills"]),
        "opportunity_recommendations": opportunity_recs,
        "skill_gap_recommendations": skill_gaps,
        "elapsed_s": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# 3. ANALYSIS
# ---------------------------------------------------------------------------

def analyze_result(result: dict, jobs: list):
    """Print detailed analysis for one user's matching result."""
    name = result["full_name"]
    city = result["city"]
    n_skills = result["num_skills"]
    elapsed = result["elapsed_s"]
    opps = result["opportunity_recommendations"]
    gaps = result["skill_gap_recommendations"]

    print(f"\n{'='*80}")
    print(f"USER: {name}  |  city={city}  |  skills={n_skills}  |  {elapsed}s")
    print(f"{'='*80}")

    if not opps:
        print("  [!] NO OPPORTUNITIES RETURNED")
        return

    print(f"\n  TOP-{len(opps)} OPPORTUNITIES:")
    print(f"  {'Rank':<5} {'Score':<8} {'Title':<40} {'Location':<15} {'Ess.Matches'}")
    print(f"  {'-'*90}")

    scores = []
    for opp in opps:
        rank = opp.get("rank", "?")
        score = opp.get("final_score", 0)
        title = (opp.get("opportunity_title") or "?")[:38]
        loc = (opp.get("location") or "?")[:13]
        ess = opp.get("matched_skills", {}).get("essential_skill_matches", [])
        ess_count = sum(1 for e in ess if e.get("meets_threshold"))
        ess_total = len(ess)
        scores.append(score)
        print(f"  {rank:<5} {score:<8.4f} {title:<40} {loc:<15} {ess_count}/{ess_total}")

    # Score differentiation
    unique_scores = len(set(round(s, 4) for s in scores))
    print(f"\n  Score range: {min(scores):.4f} – {max(scores):.4f}  |  {unique_scores} unique scores")

    # Breakdown of top result
    top = opps[0]
    bd = top.get("score_breakdown", {})
    print(f"\n  TOP RESULT BREAKDOWN:")
    print(f"    total_skill_utility = {bd.get('total_skill_utility')}")
    print(f"    skill_components    = {bd.get('skill_components')}")
    print(f"    preference_score    = {bd.get('preference_score')}")

    # Skill matches detail for top result
    ms = top.get("matched_skills", {})
    ess_matches = ms.get("essential_skill_matches", [])
    opt_matches = ms.get("optional_exact_matches", [])
    if ess_matches:
        print(f"\n  ESSENTIAL SKILL MATCHES (top result):")
        for m in ess_matches[:5]:
            user_lbl = m.get("best_user_skill_label", "?")
            job_lbl = m.get("job_skill_label", "?")
            sim = m.get("similarity", 0)
            meets = "Y" if m.get("meets_threshold") else "N"
            print(f"    [{meets}] {user_lbl} <-> {job_lbl}  sim={sim:.3f}")

    if opt_matches:
        print(f"\n  OPTIONAL SKILL MATCHES (top result):")
        for m in opt_matches[:5]:
            user_lbl = m.get("best_user_skill_label", "?")
            job_lbl = m.get("job_skill_label", "?")
            sim = m.get("similarity", 0)
            print(f"    {user_lbl} <-> {job_lbl}  sim={sim:.3f}")

    # Justification
    print(f"\n  JUSTIFICATION: {top.get('justification', 'N/A')[:200]}")

    # Skill gaps
    if gaps:
        print(f"\n  SKILL GAP RECOMMENDATIONS ({len(gaps)}):")
        for g in gaps:
            lbl = g.get("skill_label", g.get("skill_id", "?"))
            prox = g.get("proximity_score", 0)
            unlock = g.get("job_unlock_count", 0)
            comb = g.get("combined_score", 0)
            reason = g.get("reasoning", "")[:80]
            print(f"    {lbl:<35} prox={prox:.3f}  unlock={unlock:<4}  combined={comb:.3f}  {reason}")


# ---------------------------------------------------------------------------
# 4. MAIN
# ---------------------------------------------------------------------------

def main():
    client = get_mongo_client()

    print("Loading RankedJobs...")
    jobs = load_ranked_jobs(client)
    logger.info(f"Loaded {len(jobs)} jobs from RankedJobs")

    # Stats on loaded jobs
    with_ess = sum(1 for j in jobs if j["essential_skills_origin_uuids"])
    with_opt = sum(1 for j in jobs if j["optional_skills_origin_uuids"])
    with_attrs = sum(1 for j in jobs if j["attributes"])
    with_demand = sum(1 for j in jobs if j["attributes"].get("expected_demand"))
    print(f"  Jobs: {len(jobs)} total, {with_ess} with essential skills, "
          f"{with_opt} with optional skills, {with_attrs} with attributes, "
          f"{with_demand} with demand label")

    # Check how many tabiya IDs are in the embedding
    all_tabiya = set()
    for j in jobs:
        all_tabiya.update(j["essential_skills_origin_uuids"])
        all_tabiya.update(j["optional_skills_origin_uuids"])
    in_emb = sum(1 for t in all_tabiya if t in scorer_skill._embedding_ids)
    print(f"  Unique Tabiya skill IDs in jobs: {len(all_tabiya)}, in embedding: {in_emb}/{len(all_tabiya)}")

    # Nairobi/Kenya jobs count
    kenya_jobs = [j for j in jobs if "kenya" in (j.get("location") or "").lower()
                  or "nairobi" in (j.get("location") or "").lower()]
    remote_jobs = [j for j in jobs if "remote" in (j.get("location") or "").lower()]
    print(f"  Location breakdown: {len(kenya_jobs)} Kenya/Nairobi, {len(remote_jobs)} Remote")

    print("\nLoading real user profiles...")
    users = load_real_users(client)
    client.close()

    print(f"  Loaded {len(users)} users:")
    for u in users:
        n = len(u["skills_vector"]["top_skills"])
        print(f"    {u['full_name']:<20} city={u['city']:<15} skills={n:<3} src={u['_source_db']}")

    # Check user skill resolution
    print("\n  User skill → embedding resolution:")
    for u in users:
        total = len(u["skills_vector"]["top_skills"])
        resolved = 0
        for s in u["skills_vector"]["top_skills"]:
            rid = scorer_skill._resolve_id(s["originUUID"])
            if rid in scorer_skill._embedding_ids:
                resolved += 1
        print(f"    {u['full_name']:<20} {resolved}/{total} skills resolve to embedding")

    # Run matching
    print("\n" + "=" * 80)
    print("RUNNING MATCHING AGAINST RANKED JOBS")
    print("=" * 80)

    all_results = []
    for u in users:
        result = match_user_against_jobs(u, jobs)
        all_results.append(result)
        analyze_result(result, jobs)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\n{'User':<20} {'Opps':<6} {'Gaps':<6} {'Top Score':<10} {'Score Range':<15} {'Unique':<8} {'Time'}")
    print("-" * 80)
    for r in all_results:
        opps = r["opportunity_recommendations"]
        gaps = r["skill_gap_recommendations"]
        scores = [o["final_score"] for o in opps] if opps else [0]
        unique = len(set(round(s, 4) for s in scores))
        rng = f"{min(scores):.4f}-{max(scores):.4f}"
        print(f"{r['full_name']:<20} {len(opps):<6} {len(gaps):<6} {max(scores):<10.4f} {rng:<15} {unique:<8} {r['elapsed_s']}s")

    # Write full results to JSON
    output_path = backend_dir / "tests" / "test_real_results.json"
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nFull results written to {output_path}")


if __name__ == "__main__":
    main()
