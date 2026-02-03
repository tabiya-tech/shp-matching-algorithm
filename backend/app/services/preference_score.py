# backend/app/services/preference_score.py
from app.config import PREFERENCE_CONFIG # Updated import path

def calculate_preference_score(user_profile: dict, job_posting: dict) -> float:
    """
    Service Logic: Computes the S_pref score.
    S_pref = Base + (Sum * Scaling_Factor)
    """
    raw_score_sum = 0.0
    base_constant = PREFERENCE_CONFIG["base_constant"]
    
    user_weights = user_profile.get("preference_vector", {})
    job_attrs = job_posting.get("attributes", {})

    # Iterate through attribute rules defined in config
    for attr_key, settings in PREFERENCE_CONFIG["attributes"].items():
        # 1. Get Components
        beta = settings["beta"]
        user_weight = user_weights.get(attr_key, 0.0)
        job_value_raw = job_attrs.get(attr_key)

        # 2. Encoding Logic
        encoded_value = 0.0
        if settings["type"] == "dummy":
            if job_value_raw == settings["active_level"]:
                encoded_value = 1.0
        
        elif settings["type"] == "ordered_linear":
            mapping = settings.get("mapping", {})
            encoded_value = mapping.get(job_value_raw, 0.0)

        # 3. Add to Raw Sum
        raw_score_sum += (beta * user_weight * encoded_value)

    # --- SCALING LOGIC ---
    # We use a 0.2 factor to ensure the score stays within the 0.0-1.0 range
    SCALING_FACTOR = 0.2
    scaled_sum = raw_score_sum * SCALING_FACTOR
    final_pref_score = base_constant + scaled_sum
    
    return max(0.0, min(1.0, final_pref_score))