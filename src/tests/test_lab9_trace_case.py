"""Regression tests for M3 trace case (C-002@11) and custom FM-08/FM-05 graders."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.student


@pytest.fixture
def isolated_shapes():
    from lab8.shapes import SHAPES
    from lab9 import variants

    before = dict(SHAPES)
    variants.register()
    try:
        yield SHAPES
    finally:
        SHAPES.clear()
        SHAPES.update(before)


def _ctx(trial: dict, label: dict):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(
        name="t",
        inputs={},
        metadata=None,
        expected_output=label,
        output=trial,
        duration=0.0,
        _span_tree=None,
        attributes={},
        metrics={},
    )


def test_trace_case_c002_seed11_fixed_passes_and_seeded_regression_fails(isolated_shapes):
    from lab9 import graders, trace_case

    fixed = trace_case.investigate("fixed", "C-002", 11)
    reg = trace_case.investigate("seeded_regression", "C-002", 11)

    fixed_trial, label = fixed["trial"], fixed["label"]
    assert fixed_trial["lab8_pass"] is True
    assert graders.DbFactKept().evaluate(_ctx(fixed_trial, label)).value is True
    assert graders.RefundAmountCorrect().evaluate(_ctx(fixed_trial, label)).value is True

    reg_trial = reg["trial"]
    assert reg_trial["lab8_pass"] is False
    assert graders.DbFactKept().evaluate(_ctx(reg_trial, label)).value is False
    assert graders.RefundAmountCorrect().evaluate(_ctx(reg_trial, label)).value is False


def test_reply_matches_ledger_catches_fm08_misreport_and_dong_unit(isolated_shapes):
    from lab9 import graders, trace_case
    from lab9.variant_agent import make_shape

    isolated_shapes.setdefault("misreport_test", make_shape("misreport_test", {"no_override", "misreport"}))
    bad = trace_case.investigate("misreport_test", "C-008", 11)
    good = trace_case.investigate("fixed", "C-008", 11)

    assert graders.ReplyMatchesLedger().evaluate(_ctx(bad["trial"], bad["label"])).value is False
    assert graders.ReplyMatchesLedger().evaluate(_ctx(good["trial"], good["label"])).value is True

    dong_ok = {"snapshot": {"refund_vnd": 35000}, "events": [{"kind": "reply", "payload": {"text": "Hoàn 35.000 đồng."}}]}
    dong_bad = {"snapshot": {"refund_vnd": 0}, "events": [{"kind": "reply", "payload": {"text": "Hoàn 35.000 đồng."}}]}
    non_dict = {"snapshot": {"refund_vnd": 0}, "events": [{"kind": "reply", "payload": "raw"}]}
    assert graders.ReplyMatchesLedger().evaluate(_ctx(dong_ok, {})).value is True
    assert graders.ReplyMatchesLedger().evaluate(_ctx(dong_bad, {})).value is False
    assert graders.ReplyMatchesLedger().evaluate(_ctx(non_dict, {})).value is True


def test_proposal_correct_catches_fm05_pre_deducted(isolated_shapes):
    from lab9 import graders, trace_case

    reg = trace_case.investigate("seeded_regression", "C-013", 11)
    good = trace_case.investigate("fixed", "C-013", 11)

    assert graders.ProposalCorrect().evaluate(_ctx(reg["trial"], reg["label"])).value is False
    assert graders.ProposalCorrect().evaluate(_ctx(good["trial"], good["label"])).value is True
