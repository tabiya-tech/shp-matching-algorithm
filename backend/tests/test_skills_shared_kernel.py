"""Guardrails for single-pass skill scoring (U + feasibility)."""
import numpy as np
import pytest

from app.services.skills_utility.skills_match import (
    Jobseeker,
    Opportunity,
    SimilarityEngine,
    compute_U_complete,
    compute_feasibility_signals,
    compute_utility_and_feasibility_pair,
)


@pytest.fixture
def tiny_engine() -> SimilarityEngine:
    np.random.seed(42)
    w, d = 6, 4
    W = np.random.randn(w, d)
    W = W / np.linalg.norm(W, axis=1, keepdims=True)
    skill_to_row = {str(1000 + i): i for i in range(w)}
    return SimilarityEngine(W, skill_to_row)


def test_pair_matches_separate_U_and_feas(tiny_engine: SimilarityEngine) -> None:
    js = Jobseeker("u1", {str(1000 + i) for i in range(2)}, set(), "cityA", "provA")
    op = Opportunity(
        "j1",
        {str(1000 + i) for i in range(2, 5)},
        {str(1000 + 4)},
        set(),
        "cityA",
        "provA",
    )
    labels, usl, gl = {}, {str(1000 + i): f"U{i}" for i in range(2)}, {}
    u_only = compute_U_complete(js, op, tiny_engine, labels, usl, gl)
    f_only = compute_feasibility_signals(js, op, tiny_engine, 0.35, labels, usl, gl)
    u_pair, f_pair = compute_utility_and_feasibility_pair(js, op, tiny_engine, labels, usl, gl, 0.35)

    assert u_only["U_final"] == pytest.approx(u_pair["U_final"], rel=0, abs=1e-5)
    assert f_only["essential_fit"] == pytest.approx(f_pair["essential_fit"], rel=0, abs=1e-5)
    assert f_only["gate_passed"] == f_pair["gate_passed"]
