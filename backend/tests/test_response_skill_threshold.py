"""Response payload should keep only skills above configured threshold."""

from app.services import matching_service as ms


def test_filter_essential_skill_matches_uses_configured_threshold(monkeypatch):
    monkeypatch.setattr(ms, "MATCH_RESPONSE_SKILL_MIN_SCORE", 0.6)
    match_details = {
        "essential_skill_matches": [
            {"job_skill_id": "a", "similarity": 0.8, "meets_threshold": True},
            {"job_skill_id": "b", "similarity": 0.6, "meets_threshold": True},
            {"job_skill_id": "c", "similarity": 0.59, "meets_threshold": True},
            {"job_skill_id": "d", "similarity": 0.0, "meets_threshold": False},
        ]
    }

    out = ms._filter_essential_skill_matches(match_details)

    assert [x["job_skill_id"] for x in out] == ["a", "b"]


def test_filter_skill_gap_recommendations_uses_configured_threshold(monkeypatch):
    monkeypatch.setattr(ms, "MATCH_RESPONSE_SKILL_MIN_SCORE", 0.5)
    monkeypatch.setattr(ms, "MATCH_TOP_K_SKILL_GAPS", 2)
    skill_gaps = [
        {"skill_id": "s1", "proximity_score": 0.9},
        {"skill_id": "s2", "proximity_score": 0.5},
        {"skill_id": "s3", "proximity_score": 0.49},
    ]

    out = ms._filter_skill_gap_recommendations(skill_gaps)

    assert [x["skill_id"] for x in out] == ["s1", "s2"]
