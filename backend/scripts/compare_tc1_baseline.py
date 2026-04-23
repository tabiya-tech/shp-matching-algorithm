"""One-off: run TC1 user and print top-1 occupation + opportunity metrics for diff vs saved baseline."""
import asyncio
import os
import sys
from pathlib import Path

# backend/ as cwd
os.chdir(Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.matching_service import match_user_with_data
from app.database import get_all_jobs, get_all_occupations

TC1 = {
    "user_id": "tc1_software_dev_nairobi",
    "city": "Nairobi",
    "province": "Nairobi",
    "skills_vector": {
        "top_skills": [
            {"preferredLabel": "Python (computer programming)", "originUUID": "687671bdebd2bf665349d1aa", "proficiency": 0.95},
            {"preferredLabel": "JavaScript", "originUUID": "687671b5ebd2bf665349b33b", "proficiency": 0.90},
            {"preferredLabel": "SQL", "originUUID": "687671b5ebd2bf665349b956", "proficiency": 0.85},
            {"preferredLabel": "TypeScript", "originUUID": "687671b9ebd2bf665349c2f1", "proficiency": 0.80},
            {"preferredLabel": "DevOps", "originUUID": "687671bdebd2bf665349d91b", "proficiency": 0.75},
            {"preferredLabel": "Agile development", "originUUID": "687671bdebd2bf665349d4b6", "proficiency": 0.80},
            {"preferredLabel": "manage database", "originUUID": "687671b5ebd2bf665349af35", "proficiency": 0.70},
            {"preferredLabel": "PostgreSQL", "originUUID": "687671baebd2bf665349ca22", "proficiency": 0.75},
        ]
    },
    "skill_groups_origin_uuids": [],
    "preference_vector": {
        "earnings_per_month": 0.9,
        "task_content": 1.0,
        "physical_demand": 0.0,
        "work_flexibility": 0.9,
        "social_interaction": 0.2,
        "career_growth": 0.9,
        "social_meaning": 0.3,
    },
}

BASELINE_OCC1 = {"uuid": "3511_Nairobi", "final_score": 0.5695, "u_hat": 0.9168, "p_hat": 0.6212}
BASELINE_OPP1 = {"uuid": "69b863117f0c00e65d78afad", "final_score": 0.8755, "u_hat": 0.9168, "p_hat": 0.955}


async def main() -> None:
    jobs, occ = await asyncio.gather(get_all_jobs(), get_all_occupations())
    out = match_user_with_data(TC1, jobs, occ)
    occ1 = (out.get("occupation_recommendations") or [None])[0]
    if not occ1:
        print("No occupation recs (empty list)")
        return
    sb = occ1.get("score_breakdown") or {}
    print("top_occupation", occ1.get("uuid"), "final_score", occ1.get("final_score"))
    print("  u_hat", sb.get("u_hat"), "p_hat", sb.get("p_hat"))
    print("  total_skill_utility", sb.get("total_skill_utility"), "ess", (sb.get("skill_components") or {}).get("ess"))
    d = (BASELINE_OCC1["final_score"] - float(occ1.get("final_score", 0))) if occ1.get("final_score") is not None else None
    if d is not None:
        print("  delta vs saved baseline occ final_score", round(d, 6))

    opp1 = (out.get("opportunity_recommendations") or [None])[0]
    if opp1:
        osb = opp1.get("score_breakdown") or {}
        print("top_opportunity", opp1.get("uuid"), "final_score", opp1.get("final_score"))
        print("  u_hat", osb.get("u_hat"), "p_hat", osb.get("p_hat"))
        if opp1.get("uuid") == BASELINE_OPP1["uuid"]:
            d2 = BASELINE_OPP1["final_score"] - float(opp1.get("final_score", 0))
            print("  delta vs saved baseline final_score", round(d2, 6))


if __name__ == "__main__":
    # Load dotenv from app
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
