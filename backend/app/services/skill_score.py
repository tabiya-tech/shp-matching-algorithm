# backend/app/services/skill_score.py
import torch
import json
import numpy as np
from app.services.skills_utility.skills_match import Jobseeker, Opportunity, SimilarityEngine, compute_U_complete

# Global engine variable to hold the model in memory
_engine = None

def init_skill_engine():
    """
    Loads the AI model into memory once. 
    This is called when the FastAPI server starts.
    """
    global _engine
    if _engine is not None:
        return _engine

    MODEL_PATH = "app/services/skills_utility/Output/skill_embedding_model.pt"
    MAPPING_PATH = "app/services/skills_utility/Output/skill_to_row.json"
    
    # Load and normalize the weights
    state = torch.load(MODEL_PATH, map_location="cpu")
    W = state['state_dict']['embedding.weight'].numpy()
    norms = np.linalg.norm(W, axis=1, keepdims=True)
    W = W / np.where(norms > 0, norms, 1.0)
    
    with open(MAPPING_PATH, 'r') as f:
        skill_to_row = json.load(f)
            
    _engine = SimilarityEngine(W, skill_to_row)
    print("✅ Skill Matching Engine Loaded Successfully")
    return _engine

def calculate_skill_score(user_profile: dict, job_posting: dict) -> dict:
    """
    Service Logic: Uses the pre-loaded engine to compute matches.
    """
    engine = init_skill_engine() # Ensures engine is ready
    
    js = Jobseeker(
        compass_id=user_profile["youth_id"],
        skills_origin_uuids={s["originUUID"] for s in user_profile['skills_vector']['top_skills']},
        skill_groups_origin_uuids=set(user_profile.get("skill_groups_origin_uuids", [])),
        city=user_profile.get("city"),
        province=user_profile.get("province")
    )
    
    op = Opportunity(
        opportunity_id=job_posting["uuid"],
        essential_skills_origin_uuids=set(job_posting["essential_skills_origin_uuids"]),
        optional_skills_origin_uuids=set(job_posting.get("optional_skills_origin_uuids", [])),
        skill_groups_origin_uuids=set(job_posting.get("skill_groups_origin_uuids", [])),
        city=job_posting.get("location"), 
        province=job_posting.get("location") 
    )

    return compute_U_complete(js, op, engine)