"""Bonus parity tests: Inspect AI graders vs pydantic-evals (skipped when inspect-ai is absent)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.student


def test_inspect_ai_graders_match_pydantic_evals():
    pytest.importorskip("inspect_ai")
    from bonus.inspect_graders import run_comparison

    results = run_comparison()
    assert len(results) == 5
    for res in results:
        assert res["cases"] == 70
        assert res["mismatches"] == []
        assert res["inspect_ai"] == res["pydantic_evals"]
