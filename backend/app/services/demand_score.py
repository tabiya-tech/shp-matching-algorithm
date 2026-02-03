# backend/app/services/demand_score.py
from app.config import DEMAND_SCORE_MAPPING

def calculate_demand_score(job_posting: dict) -> float:
    """
    Computes the S_demand score for a single job posting.
    This is now a standalone function ready for API calls.
    """
    # 1. Safely extract the attributes dictionary
    attributes = job_posting.get("attributes", {})
    
    # 2. Get the specific demand label
    demand_label = attributes.get("expected_demand")
    
    # 3. Map label to value using the global mapping
    if demand_label and demand_label in DEMAND_SCORE_MAPPING:
        return DEMAND_SCORE_MAPPING[demand_label]
        
    # 4. Fallback / Default
    return 0.5