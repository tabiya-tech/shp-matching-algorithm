#!/usr/bin/env python3
"""
CORE UTILITY CALCULATION ENGINE (U)

DESCRIPTION:
This script implements a Content-Based Utility Model designed to rank jobseekers 
against opportunities based on four core dimensions:

1. Essential Skill Proximity ($U_{ess}$): Uses the Best-Mean Cosine Similarity. 
   For every essential skill a job requires, the engine finds the youth's most 
   mathematically similar skill from the Node2Vec embedding space and averages 
   these "best matches".

2. Optional Skill Proximity ($U_{opt}$): Uses Mean-Vector Cosine Similarity. 
   It calculates the "centroid" (average vector) of all a seeker's skills and 
   compares it to the centroid of the job's optional skills to measure thematic 
   alignment.

3. Skill Group Recall ($U_{grp}$): A simple overlap metric that rewards 
   jobseekers for possessing skills within the specific competency groups 
   defined by the job.

4. Location Utility ($U_{loc}$): A geographic heuristic that assigns a score 
   of 1.0 for a city match, 0.7 for a province match, and 0.3 otherwise.

SCORING LOGIC:
The final score is a weighted average of these components, which is then 
subjected to a Soft Penalty. This penalty reduces the score based on the 
"Gap Share"—the percentage of essential skills that fall below a similarity 
threshold of 0.35.
"""

import torch
import json
import numpy as np
from typing import Set, Dict, Optional
from dataclasses import dataclass

# =============================================================================
# 1) DATA STRUCTURES
# =============================================================================

@dataclass(frozen=True)
class Jobseeker:
    compass_id: str
    skills_origin_uuids: Set[str]
    skill_groups_origin_uuids: Set[str]
    city: Optional[str] = None
    province: Optional[str] = None

@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str
    essential_skills_origin_uuids: Set[str]
    optional_skills_origin_uuids: Set[str]
    skill_groups_origin_uuids: Set[str]
    city: Optional[str] = None
    province: Optional[str] = None

# =============================================================================
# 2) COMPONENT HELPERS
# =============================================================================

def location_near_enough(js: Jobseeker, op: Opportunity) -> float:
    """Calculates geographic proximity score based on city/province."""
    s_city = (js.city or "").strip().casefold()
    s_prov = (js.province or "").strip().casefold()
    o_city = (op.city or "").strip().casefold()
    o_prov = (op.province or "").strip().casefold()
    
    if s_city and o_city and s_city == o_city:
        return 1.0  # Exact city match
    if s_prov and o_prov and s_prov == o_prov:
        return 0.7  # Province match
    return 0.3      # Baseline/No match

# =============================================================================
# 3) SIMILARITY ENGINE
# =============================================================================

class SimilarityEngine:
    """Handles the high-dimensional vector math for skill proximity."""
    def __init__(self, W: np.ndarray, skill_to_row: Dict[str, int]):
        self.W = W  # Row-normalised embedding matrix
        self.skill_to_row = skill_to_row

    def _rows(self, skill_ids) -> np.ndarray:
        """Retrieves vectors for specific skill IDs from the matrix."""
        idx = [self.skill_to_row[str(s)] for s in skill_ids if str(s) in self.skill_to_row]
        if not idx:
            return np.empty((0, self.W.shape[1]))
        return self.W[np.array(idx), :]

    def _mean_unit(self, M: np.ndarray) -> Optional[np.ndarray]:
        """Calculates the unit-normalised mean vector of a set."""
        if M.size == 0: return None
        v = M.mean(axis=0)
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else None

    @staticmethod
    def best_mean_cos(op_mat: np.ndarray, js_mat: np.ndarray):
        """Essential skill matching: best-match per required skill."""
        if op_mat.size == 0 or js_mat.size == 0:
            return 0.0, None
        S = op_mat @ js_mat.T
        np.maximum(S, 0.0, out=S) # Clip negative similarities
        rowmax = S.max(axis=1)    # Max similarity for each job skill
        return float(rowmax.mean()), rowmax

# =============================================================================
# 4) CORE UTILITY CALCULATION
# =============================================================================

def compute_U_complete(js: Jobseeker, op: Opportunity, engine: SimilarityEngine):
    """Calculates the final Utility score with components and penalties."""
    
    # Weights and Tunables from the original project settings
    W_LOC, W_ESS, W_OPT, W_GRP, W_GAP_PEN = 0.20, 0.50, 0.20, 0.10, 0.50
    TAU_ELIG = 0.35      # Similarity threshold for 'matching'
    MIN_ESS_SHARE = 1.0  # Fraction of essentials required for eligibility

    # 1. Location Utility
    loc_score = location_near_enough(js, op)

    # 2. Skill Matrices and Vectors
    js_mat = engine._rows(js.skills_origin_uuids)
    ess_mat = engine._rows(op.essential_skills_origin_uuids)
    
    # 3. Essential Skill Similarity (Best-of Cosine)
    ess_sim, ess_rowmax = engine.best_mean_cos(ess_mat, js_mat)
    
    # 4. Optional Skill Similarity (Centroid Cosine)
    js_mean = engine._mean_unit(js_mat)
    opt_vec = engine._mean_unit(engine._rows(op.optional_skills_origin_uuids))
    opt_sim = max(0.0, float(js_mean @ opt_vec)) if js_mean is not None and opt_vec is not None else 0.0

    # 5. Skill Group Recall
    grp_sim = 0.0
    if op.skill_groups_origin_uuids:
        inter = len(op.skill_groups_origin_uuids & js.skill_groups_origin_uuids)
        grp_sim = inter / len(op.skill_groups_origin_uuids)

    # --- Aggregation ---
    core_score = (
        W_LOC * loc_score + W_ESS * ess_sim + W_OPT * opt_sim + W_GRP * grp_sim
    ) / (W_LOC + W_ESS + W_OPT + W_GRP)

    # --- Penalty & Eligibility ---
    if ess_rowmax is None or ess_rowmax.size == 0:
        gap_share, eligible = 0.0, True
    else:
        meets = (ess_rowmax >= TAU_ELIG)
        gap_share = float((~meets).mean())
        eligible = (float(meets.mean()) >= MIN_ESS_SHARE)

    # Apply Soft Penalty
    u_final = max(0.0, core_score - (W_GAP_PEN * gap_share))

    return {
        "U_final": round(u_final, 4),
        "is_eligible": eligible,
        "components": {
            "loc": round(loc_score, 2),
            "ess": round(ess_sim, 4),
            "opt": round(opt_sim, 4),
            "grp": round(grp_sim, 4)
        },
        "penalty": round(W_GAP_PEN * gap_share, 4)
    }