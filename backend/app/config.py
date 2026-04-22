# src/config.py


# ---------------------------------------------------------------------------
# Scoring mode: "multiplicative" (U*P, paper-aligned) or "additive" (legacy)
# ---------------------------------------------------------------------------
SCORING_MODE = "multiplicative"

# Legacy additive weights — kept for backward-compatibility / A-B testing.
GLOBAL_WEIGHTS = {
    "w1_skills": 0.40,
    "w2_preference": 0.40,
    "w3_market": 0.20
}

# ---------------------------------------------------------------------------
# Success-propensity proxy config  (p_hat = G * E^alpha * R^beta * M^gamma)
# ---------------------------------------------------------------------------
SUCCESS_PROPENSITY_CONFIG = {
    "alpha_essential": 0.5,      # exponent for essential-skill fit (E_ij)
    "beta_readiness": 0.2,       # exponent for recruiter-side readiness (R_ij)
    "gamma_market": 0.3,         # exponent for market opportunity (M_ij)
    "gate_threshold": 0.35,      # similarity threshold for the hard gate
}

# 2. Demand Score Mapping (PDF Page 2, Top Table)
DEMAND_SCORE_MAPPING = {
    "Very Low Expected Demand": 0.10,
    "Low Expected Demand": 0.25,
    "Moderate Expected Demand": 0.5,
    "High Expected Demand": 0.75,
    "Very High Expected Demand": 1.0
}

# 3. Preference Model Configuration (PDF Page 2 & 4)
#
# Each attribute has an "enabled" flag.  Set to False to exclude it from
# scoring without removing the definition (easy to re-enable later).
# The sigmoid scaling factor is computed dynamically from the enabled
# attributes so the score range stays stable regardless of how many
# attributes are active.
PREFERENCE_CONFIG = {
    "base_constant": 0.5, # Fixed at 0.5 (PDF Page 2, Section 2)
    "attributes": {
        "earnings_per_month": {
            "enabled": True,
            "type": "ordered_linear",
            "beta": 0.5,
            "mapping": {
                "earn_15k": 0.10,
                "earn_30k": 0.33,
                "earn_50k": 0.67,
                "earn_70k": 1.0
            }
        },
        "task_content": {
            "enabled": False,
            "type": "dummy",
            "beta": 0.2,
            "active_level": "task_creative"
        },
        "physical_demand": {
            "enabled": True,
            "type": "dummy",
            "beta": -0.4,
            "active_level": "phys_heavy"
        },
        "work_flexibility": {
            "enabled": False,
            "type": "dummy",
            "beta": 0.4,
            "active_level": "flex_high"
        },
        "social_interaction": {
            "enabled": True,
            "type": "dummy",
            "beta": 0.1,
            "active_level": "soc_people"
        },
        "career_growth": {
            "enabled": True,
            "type": "dummy",
            "beta": 0.5,
            "active_level": "growth_high"
        },
        "social_meaning": {
            "enabled": False,
            "type": "dummy",
            "beta": 0.3,
            "active_level": "mean_high"
        }
    }
}