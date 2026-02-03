from fastapi import FastAPI
from app.schemas import MatchRequest, MatchResponse
from app.config import GLOBAL_WEIGHTS
from app.services.skill_score import calculate_skill_score, init_skill_engine
from app.services.preference_score import calculate_preference_score
from app.services.demand_score import calculate_demand_score
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Tabiya Matching Service")

# Add this block
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, this allows your React app to connect
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Startup: Load the AI model once so it stays in memory
@app.on_event("startup")
async def startup_event():
    init_skill_engine()

@app.get("/")
def health_check():
    return {"status": "online", "message": "Tabiya Matching Engine is active"}

# 2. The Matching Endpoint: Replaces your giant loop
@app.post("/match", response_model=MatchResponse)
async def match_endpoint(request: MatchRequest):
    user = request.user_profile
    jobs = request.available_jobs
    user_recs = []

    for job_obj in jobs:
        # Pydantic objects need to be converted to dicts for your logic
        job = job_obj.dict()
        
        # --- A. SKILLS SCORE ---
        skill_result = calculate_skill_score(user, job)
        s_skills = skill_result["U_final"]

        # --- B. PREFERENCE SCORE ---
        s_pref = calculate_preference_score(user, job)

        # --- C. DEMAND SCORE ---
        s_demand = calculate_demand_score(job)

        # --- COMPUTE FINAL WEIGHTED SCORE ---
        final_score = (
            (GLOBAL_WEIGHTS["w1_skills"] * s_skills) +
            (GLOBAL_WEIGHTS["w2_preference"] * s_pref) +
            (GLOBAL_WEIGHTS["w3_market"] * s_demand)
        )

        user_recs.append({
            "uuid": job.get("uuid"),
            "originUuid": job.get("originUuid"),
            "opportunity_title": job.get("opportunity_title"),
            "location": job.get("location"),
            "is_eligible": skill_result["is_eligible"],
            "final_score": round(final_score, 4),
            "score_breakdown": {
                "total_skill_utility": round(skill_result["U_final"], 4),
                "preference_score": round(s_pref, 4),
                "demand_score": round(s_demand, 4)
            }
        })

    # 3. Rank and Filter (Top 10)
    user_recs.sort(key=lambda x: x['final_score'], reverse=True)
    
    return {
        "user_id": user.get('youth_id', 'unknown'),
        "opportunity_recommendations": user_recs[:10]
    }