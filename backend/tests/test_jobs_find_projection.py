"""Ranked job Mongo projection stays aligned with build_job_dict_from_ranked."""

from app.database import RANKED_JOB_FIND_PROJECTION, build_job_dict_from_ranked


def test_projection_includes_core_paths():
    assert RANKED_JOB_FIND_PROJECTION["job_id"] == 1
    assert RANKED_JOB_FIND_PROJECTION["llm_classified_skills"] == 1
    assert RANKED_JOB_FIND_PROJECTION["onet_work_activities"] == 1
    assert RANKED_JOB_FIND_PROJECTION["classifier_metadata.city"] == 1


def test_build_job_identical_for_projection_shaped_document():
    """Simulate Mongo return shape when only projected paths are present (nested meta)."""
    rd = {
        "job_id": "proj-1",
        "is_active": True,
        "classifier_metadata": {
            "title": "Analyst",
            "city": "Nairobi",
            "county": "Nairobi",
            "employer": "Co",
            "employment_type": "full_time",
            "salary": "50k",
            "closing_date": "2026-01-01",
            "application_url": "https://x",
            "job_description": "Do work",
            "description": "",
        },
        "llm_classified_skills": {
            "essential": [{"tabiya_skill_id": "e1"}],
            "optional": [{"tabiya_skill_id": "o1"}],
        },
        "llm_job_attributes": {"attributes": {"task_content": "mid"}},
        "onet_work_activities": [{"id": "WA1", "name": "Reading"}],
        "skill_groups_origin_uuids": ["g1"],
    }
    j = build_job_dict_from_ranked(rd)
    assert j is not None
    assert j["uuid"] == "proj-1"
    assert j["city"] == "Nairobi"
    assert j["essential_skills_origin_uuids"] == ["e1"]
    assert j["onet_work_activities"][0]["id"] == "WA1"
