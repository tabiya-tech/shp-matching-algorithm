import logging
import os
import json
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

# Load from environment
MONGO_URL = os.getenv("MONGO_URL")
DATABASE_NAME = os.getenv("MONGO_DB_NAME")

if not MONGO_URL:
    raise ValueError("MONGO_URL environment variable is not set")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DATABASE_NAME]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Work-activity enrichment: look up importance/level from occupation taxonomy
# ---------------------------------------------------------------------------
_wa_lookup = None  # {occupation_label_lower: {WA_code: {importance, level}}}
_wa_averages = None  # {WA_code: {importance, level}} — fallback for unmatched


def _load_wa_lookup():
    """Build WA importance/level lookup from the occupation taxonomy JSON.

    Returns (per_occupation_lookup, cross_occupation_averages).
    """
    global _wa_lookup, _wa_averages
    if _wa_lookup is not None:
        return _wa_lookup, _wa_averages

    json_path = os.path.join(os.path.dirname(__file__), "..", "data", "combined_occupation_database_with_wa.json")
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    per_occ = {}
    from collections import defaultdict
    sums = defaultdict(lambda: {"imp": 0.0, "lvl": 0.0, "n": 0})

    for entry in raw:
        label = entry.get("occupation", {}).get("preferred_label", "").lower().strip()
        wa_dict = {}
        for w in entry.get("onet_work_activities", []):
            code = w.get("WA_code")
            imp = w.get("WA_Importance", "")
            lvl = w.get("WA_Level", "")
            if code and imp and lvl and imp != "" and lvl != "":
                imp_f, lvl_f = float(imp), float(lvl)
                wa_dict[code] = {"importance": imp_f, "level": lvl_f}
                sums[code]["imp"] += imp_f
                sums[code]["lvl"] += lvl_f
                sums[code]["n"] += 1
        if wa_dict:
            per_occ[label] = wa_dict

    averages = {}
    for code, s in sums.items():
        averages[code] = {
            "importance": round(s["imp"] / s["n"], 2),
            "level": round(s["lvl"] / s["n"], 2),
        }

    _wa_lookup = per_occ
    _wa_averages = averages
    logger.info("Built WA lookup: %d occupations, %d WA codes", len(per_occ), len(averages))
    return per_occ, averages


def _enrich_work_activities(wa_items: list, classified_occupations: list) -> list:
    """Attach importance/level to a job's work activity items.

    Strategy:
      1. If the job has a classified occupation that matches the taxonomy → use
         that occupation's importance/level per WA code.
      2. Otherwise → use the cross-occupation average for each WA code.
    """
    per_occ, averages = _load_wa_lookup()

    # Try to find a matching occupation
    occ_wa = None
    for co in classified_occupations:
        label = (co.get("label") or "").lower().strip()
        if label in per_occ:
            occ_wa = per_occ[label]
            break

    enriched = []
    for item in wa_items:
        code = item.get("id")
        if not code:
            continue
        if occ_wa and code in occ_wa:
            vals = occ_wa[code]
        elif code in averages:
            vals = averages[code]
        else:
            vals = {"importance": 3.5, "level": 3.5}

        enriched.append({
            "WA_code": code,
            "WA_label": item.get("name", ""),
            "WA_Importance": vals["importance"],
            "WA_Level": vals["level"],
        })

    return enriched


def get_database():
    return db


async def get_all_jobs():
    """Fetch jobs by joining RankedJobs (skills + attributes) with ScrapedJobs (metadata).

    RankedJobs contains:
      - llm_classified_skills.essential/optional[].tabiya_skill_id  (matches embedding)
      - llm_job_attributes.attributes  (preference-scoring attributes)
    ScrapedJobs contains:
      - title, location, employer, employment_type, description, etc.
    """
    scraped_cursor = db["ScrapedJobs"].find({})
    scraped_docs = await scraped_cursor.to_list(length=5000)
    scraped_map = {str(s["_id"]): s for s in scraped_docs}

    ranked_cursor = db["RankedJobs"].find({})
    ranked_docs = await ranked_cursor.to_list(length=5000)

    jobs = []
    for rd in ranked_docs:
        job_id = str(rd.get("job_id", ""))
        scraped = scraped_map.get(job_id, {})

        lcs = rd.get("llm_classified_skills", {})
        essential_ids = [
            s["tabiya_skill_id"]
            for s in lcs.get("essential", [])
            if s.get("tabiya_skill_id")
        ]
        optional_ids = [
            s["tabiya_skill_id"]
            for s in lcs.get("optional", [])
            if s.get("tabiya_skill_id")
        ]

        llm_attrs = rd.get("llm_job_attributes", {})
        attributes = llm_attrs.get("attributes", {})

        location = scraped.get("location") or ""

        # Enrich work activities with importance/level from occupation taxonomy
        wa_items = rd.get("work_activity", {}).get("items", [])
        classified_occs = rd.get("classified_occupations", [])
        onet_wa = _enrich_work_activities(wa_items, classified_occs) if wa_items else []

        jobs.append({
            "uuid": job_id,
            "opportunity_title": scraped.get("title", "Unknown"),
            "location": location,
            "city": location,
            "province": location,
            "employer": scraped.get("employer"),
            "employment_type": scraped.get("employment_type"),
            "salary_text": scraped.get("salary_text"),
            "closing_date": str(scraped.get("closing_date", "")),
            "contract_type": scraped.get("employment_type", "full_time"),
            "url": scraped.get("application_url"),
            "essential_skills_origin_uuids": essential_ids,
            "optional_skills_origin_uuids": optional_ids,
            "skill_groups_origin_uuids": [],
            "attributes": attributes,
            "opportunity_description": scraped.get("description", ""),
            "onet_work_activities": onet_wa,
        })

    logger.info("Loaded %d jobs from RankedJobs + ScrapedJobs", len(jobs))
    return jobs


_cached_occupations = None


async def get_all_occupations():
    """Load occupations from local JSON and flatten into the format expected by _match_items.

    The raw JSON has nested structure:
      { occupation: {code, preferred_label, ...},
        skills: {essential: {uuids, labels}, optional: {uuids, labels}},
        counties_data: [{county, job_attributes}, ...] }

    We flatten each occupation × county into one item with:
      uuid, occupation_label, city, province, essential_skills_origin_uuids,
      optional_skills_origin_uuids, attributes, etc.
    """
    global _cached_occupations

    if _cached_occupations is None:
        try:
            json_path = os.path.join(os.path.dirname(__file__), "..", "data", "combined_occupation_database_with_wa.json")
            with open(json_path, "r", encoding="utf-8") as f:
                raw_occupations = json.load(f)

            flattened = []
            for entry in raw_occupations:
                occ = entry.get("occupation", {})
                skills = entry.get("skills", {})
                ess_uuids = skills.get("essential", {}).get("uuids", []) if isinstance(skills.get("essential"), dict) else []
                opt_uuids = skills.get("optional", {}).get("uuids", []) if isinstance(skills.get("optional"), dict) else []
                counties = entry.get("counties_data", [])

                code = occ.get("code", "")
                label = occ.get("preferred_label", "Unknown")
                description = occ.get("description", "")

                raw_wa = entry.get("onet_work_activities", [])
                onet_wa = []
                for w in raw_wa:
                    wc = w.get("WA_code")
                    imp = w.get("WA_Importance", "")
                    lvl = w.get("WA_Level", "")
                    if wc and imp != "" and lvl != "":
                        onet_wa.append({
                            "WA_code": wc,
                            "WA_label": w.get("WA_label", ""),
                            "WA_Importance": float(imp),
                            "WA_Level": float(lvl),
                        })

                if not counties:
                    counties = [{"county": "", "job_attributes": {}}]

                for cd in counties:
                    county = cd.get("county", "")
                    job_attrs = cd.get("job_attributes", {})
                    attrs_raw = job_attrs.get("attributes", [])
                    attributes = {}
                    if isinstance(attrs_raw, list):
                        for a in attrs_raw:
                            name = a.get("attribute_name")
                            val = a.get("selected_level_id")
                            if name and val:
                                attributes[name] = val
                    elif isinstance(attrs_raw, dict):
                        attributes = attrs_raw

                    flattened.append({
                        "uuid": f"{code}_{county}" if county else code,
                        "originUuid": code,
                        "occupation_label": label,
                        "preferredLabel": label,
                        "description": description,
                        "location": county,
                        "city": county,
                        "province": county,
                        "essential_skills_origin_uuids": ess_uuids,
                        "optional_skills_origin_uuids": opt_uuids,
                        "skill_groups_origin_uuids": [],
                        "attributes": attributes,
                        "onet_work_activities": onet_wa,
                    })

            _cached_occupations = flattened
            logger.info("Loaded %d occupation-county items from %d raw occupations", len(flattened), len(raw_occupations))
        except Exception as e:
            logger.exception(e)
            raise RuntimeError(f"Failed to load occupations: {e}")

    return _cached_occupations


async def close_mongo_connection():
    client.close()
