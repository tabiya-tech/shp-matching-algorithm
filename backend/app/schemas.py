from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# 1. Define what a single Job looks like in the incoming request
class JobOpportunity(BaseModel):
    uuid: str
    originUuid: Optional[str] = None
    opportunity_title: str
    location: Optional[str] = None
    # This allows for the flexible 'attributes' dictionary we use in demand/pref logic
    attributes: Dict[str, Any] = {}
    essential_skills_origin_uuids: List[str] = []
    optional_skills_origin_uuids: List[str] = []
    skill_groups_origin_uuids: List[str] = []

# 2. Define the "Payload" (The Match Request)
class MatchRequest(BaseModel):
    user_profile: Dict[str, Any]
    available_jobs: List[JobOpportunity]

# 3. Define the "Score Breakdown" for the response
class ScoreBreakdown(BaseModel):
    total_skill_utility: float
    preference_score: float
    demand_score: float

# 4. Define the formatted recommendation output
class OpportunityRecommendation(BaseModel):
    uuid: str
    originUuid: Optional[str] = None
    rank: Optional[int] = None
    opportunity_title: str
    location: Optional[str] = None
    is_eligible: bool
    final_score: float
    score_breakdown: ScoreBreakdown

# 5. Define the final "Answer" (The Match Response)
class MatchResponse(BaseModel):
    user_id: str
    opportunity_recommendations: List[OpportunityRecommendation]