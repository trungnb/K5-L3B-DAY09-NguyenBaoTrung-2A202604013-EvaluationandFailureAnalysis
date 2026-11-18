"""Extra M5-M7 tests for hidden-style traps, slice tampering, quiet_override, and FM-08 in v2."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

pytestmark = pytest.mark.student

ROWS = [
    {"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["denial"] if i < 2 else []}
    for i in range(4)
    for s in (1, 2)
]
SPEC = {
    "eval_set_version": "v2",
    "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True, "threshold": {"min": 0.8}}],
}


def _report(rows, metrics, items=4, seeds=(1, 2), failures=()):
    return {
        "manifest": {"eval_set_sha": "x", "items": items, "seeds": list(seeds)},
        "rows": rows,
        "metrics": metrics,
        "evaluator_failures": list(failures),
    }


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


def test_pass_k_rejects_bool_and_float():
    from lab9 import stats

    for bad in [(True, True, True), (5, True, 1), (5.0, 2, 1), (5, 2.5, 1), (5, 2, float("nan"))]:
        with pytest.raises(ValueError):
            stats.pass_at_k(*bad)
        with pytest.raises(ValueError):
            stats.pass_hat_k(*bad)


def test_integrity_flags_duplicate_rows_eval_failures_metric_tamper_nan_ratchet():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})

    dup_rows = copy.deepcopy(ROWS[:-1]) + [copy.deepcopy(ROWS[0])]
    assert gate.integrity_check(_report(dup_rows, {"pass_rate": 1.0}), base, SPEC)

    failed_eval = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0}, failures=["E-000@1:TrialPass:boom"])
    assert gate.integrity_check(failed_eval, base, SPEC)

    tampered_slices = copy.deepcopy(ROWS)
    tampered_slices[0]["slices"] = []
    assert gate.integrity_check(_report(tampered_slices, {"pass_rate": 1.0}), base, SPEC)

    bad_rows = copy.deepcopy(ROWS)
    bad_rows[0]["pass_rate"] = False
    assert gate.integrity_check(_report(bad_rows, {"pass_rate": 1.0}), base, SPEC)

    bad_cost_rows = copy.deepcopy(ROWS)
    bad_cost_rows[0]["pass_rate"] = False
    bad_cost_rows[0]["cost"] = "bad"
    assert gate.integrity_check(_report(bad_cost_rows, {"pass_rate": 1.0}), base, SPEC)

    nan_spec = copy.deepcopy(SPEC)
    nan_spec["metrics"][0]["threshold"]["min"] = float("nan")
    assert gate.integrity_check(base, base, nan_spec, SPEC)


def test_v2_gate_blocks_quiet_override_and_misreport(isolated_shapes):
    from lab9 import eval as lab9_eval, gate
    from lab9.variant_agent import make_shape

    spec = lab9_eval.load_spec(Path("config/metric_spec_v2.yaml"))
    base = lab9_eval.run_eval("swarm", spec)

    isolated_shapes.setdefault("quiet_override_test", make_shape("quiet_override_test", {"quiet_override"}))
    isolated_shapes.setdefault("misreport_v2_test", make_shape("misreport_v2_test", {"no_override", "misreport"}))

    blocked_quiet, _ = gate.check(lab9_eval.run_eval("quiet_override_test", spec), base, spec)
    blocked_misreport, _ = gate.check(lab9_eval.run_eval("misreport_v2_test", spec), base, spec)

    assert blocked_quiet
    assert "reply_matches_ledger" in blocked_misreport
