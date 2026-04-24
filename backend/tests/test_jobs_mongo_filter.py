"""Unit tests for Mongo prefilter used by get_all_jobs_with_timing(users=...)."""

from app.database import build_mongo_filter_active_and_location


def test_build_filter_empty_users_means_none():
    assert build_mongo_filter_active_and_location([]) is None


def test_build_filter_one_user_has_active_and_or():
    f = build_mongo_filter_active_and_location(
        [{"city": "Nairobi", "province": "Kenya", "user_id": "1"}]
    )
    assert f is not None
    assert f["$and"][0] == {"is_active": True}
    ors = f["$and"][1]["$or"]
    assert any("remote" in str(x) for x in ors)
    assert len(ors) >= 4


def test_build_filter_no_user_geo_is_remote_only():
    f = build_mongo_filter_active_and_location([{"user_id": "x"}])
    ors = f["$and"][1]["$or"]
    assert len(ors) == 2


def test_build_filter_two_users_unions_clauses():
    f = build_mongo_filter_active_and_location(
        [
            {"city": "A", "province": "B"},
            {"city": "C", "province": "D"},
        ]
    )
    ors = f["$and"][1]["$or"]
    assert len(ors) >= 4
