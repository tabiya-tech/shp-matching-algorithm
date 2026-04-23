"""Unit tests for RankedJobs → flat job dict (classifier_metadata path)."""

from app.database import build_job_dict_from_ranked


def test_build_job_maps_classifier_metadata_and_llm_fields():
    rd = {
        "job_id": "abc123",
        "is_active": True,
        "classifier_metadata": {
            "title": "Driver",
            "employer": "Bliss Resort Mombasa",
            "application_url": "https://jobwebkenya.com/jobs/x",
            "city": "Mombasa",
            "county": "Coast",
            "salary": None,
            "employment_type": "Full-time",
            "job_description": "Drive safely.",
            "closing_date": None,
        },
        "llm_classified_skills": {
            "essential": [{"tabiya_skill_id": "skill-a"}],
            "optional": [{"tabiya_skill_id": "skill-b"}],
        },
        "llm_job_attributes": {"attributes": {"earnings_per_month": "50K"}},
        "onet_work_activities": [
            {
                "WA_code": "4.A.2.a.1",
                "WA_label": "Read",
                "WA_Importance": 3.5,
                "WA_Level": 4.0,
            }
        ],
        "skill_groups_origin_uuids": ["grp-1", "grp-2"],
    }
    j = build_job_dict_from_ranked(rd)
    assert j is not None
    assert j["uuid"] == "abc123"
    assert j["opportunity_title"] == "Driver"
    assert j["employer"] == "Bliss Resort Mombasa"
    assert j["url"] == "https://jobwebkenya.com/jobs/x"
    assert j["city"] == "Mombasa"
    assert j["province"] == "Coast"
    assert j["location"] == "Mombasa Coast"
    assert j["salary_text"] is None
    assert j["closing_date"] == ""
    assert j["contract_type"] == "Full-time"
    assert j["opportunity_description"] == "Drive safely."
    assert j["essential_skills_origin_uuids"] == ["skill-a"]
    assert j["optional_skills_origin_uuids"] == ["skill-b"]
    assert j["attributes"] == {"earnings_per_month": "50K"}
    assert j["onet_work_activities"][0]["WA_code"] == "4.A.2.a.1"
    assert j["skill_groups_origin_uuids"] == ["grp-1", "grp-2"]


def test_inactive_job_skipped():
    rd = {
        "job_id": "x",
        "is_active": False,
        "llm_classified_skills": {"essential": [{"tabiya_skill_id": "s"}], "optional": []},
    }
    assert build_job_dict_from_ranked(rd) is None


def test_missing_metadata_still_produces_job_with_skills():
    """Rows without classifier_metadata behave like empty meta (backfill gap)."""
    rd = {
        "job_id": "no-meta",
        "is_active": True,
        "llm_classified_skills": {
            "essential": [{"tabiya_skill_id": "e1"}],
            "optional": [],
        },
        "llm_job_attributes": {"attributes": {}},
        "onet_work_activities": [],
        "skill_groups_origin_uuids": [],
    }
    j = build_job_dict_from_ranked(rd)
    assert j is not None
    assert j["opportunity_title"] == "Unknown"
    assert j["location"] == ""
    assert j["essential_skills_origin_uuids"] == ["e1"]
    assert j["onet_work_activities"] == []
    assert j["skill_groups_origin_uuids"] == []


def test_falls_back_description_key_in_metadata():
    rd = {
        "job_id": "z",
        "is_active": True,
        "classifier_metadata": {
            "title": "T",
            "description": "from description key",
        },
        "llm_classified_skills": {"essential": [], "optional": []},
        "llm_job_attributes": {"attributes": {}},
        "onet_work_activities": [],
        "skill_groups_origin_uuids": [],
    }
    j = build_job_dict_from_ranked(rd)
    assert j is not None
    assert j["opportunity_description"] == "from description key"
