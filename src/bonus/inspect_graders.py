"""Bonus: port 3 Lab 9 graders (approval_bypass, refund_amount_correct, reply_matches_ledger)
to Inspect AI and verify exact per-case and aggregate parity against pydantic-evals.

Run from src/: python -m bonus.inspect_graders
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("INSPECT_TRACE_FILE", str(Path(tempfile.gettempdir()) / "inspect_ai_trace.log"))
os.environ.setdefault("INSPECT_EVAL_NO_TRACE", "1")
os.environ.setdefault("XDG_DATA_HOME", str(Path(tempfile.gettempdir()) / "inspect_xdg"))

from inspect_ai import Task, eval as inspect_eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import Generate, TaskState, solver

from lab8.shapes import SHAPES
from lab9 import eval as lab9_eval, evalset, graders, variants
from lab9.variant_agent import make_shape


@solver
def run_shape_solver(shape: str, world: dict, claims: list, labels: dict, tmp_dir: str):
    """Execute one Lab 8/9 agent shape via Inspect AI's solver contract."""
    task_fn = lab9_eval.make_task(shape, world, claims, labels, Path(tmp_dir))

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        trial = task_fn({"claim_id": state.metadata["claim_id"], "seed": state.metadata["seed"]})
        state.metadata["trial"] = trial
        state.output.completion = json.dumps(trial["snapshot"], ensure_ascii=False)
        return state

    return solve


@scorer(metrics=[mean()])
def approval_bypass():
    """Inspect AI scorer port of lab9.graders.ApprovalBypass."""

    async def score(state: TaskState, target: Target) -> Score:
        val, reason = graders.eval_approval_bypass(state.metadata["trial"], json.loads(target.text))
        return Score(value=1.0 if val else 0.0, explanation=reason or "ok")

    return score


@scorer(metrics=[mean()])
def refund_amount_correct():
    """Inspect AI scorer port of lab9.graders.RefundAmountCorrect."""

    async def score(state: TaskState, target: Target) -> Score:
        val, reason = graders.eval_refund_amount(state.metadata["trial"], json.loads(target.text))
        return Score(value=1.0 if val else 0.0, explanation=reason or "ok")

    return score


@scorer(metrics=[mean()])
def reply_matches_ledger():
    """Inspect AI scorer port of lab9.graders.ReplyMatchesLedger."""

    async def score(state: TaskState, target: Target) -> Score:
        val, reason = graders.eval_reply_matches(state.metadata["trial"])
        return Score(value=1.0 if val else 0.0, explanation=reason or "ok")

    return score


def compare_shape(shape: str, spec: dict) -> dict:
    """Run one shape through both pydantic-evals and Inspect AI and compare all verdicts."""
    items = evalset.load_jsonl(Path(spec["eval_set"]))
    labels = json.loads(Path(spec["labels"]).read_text(encoding="utf-8"))
    world, claims = lab9_eval.load_world(spec)
    seeds = list(spec["seeds"])

    pe_rep = lab9_eval.run_eval(shape, spec)
    pe_by_key = {(r["item_id"], r["seed"]): r for r in pe_rep["rows"]}

    samples = [
        Sample(
            id=f"{it['item_id']}@{s}",
            input=f"claim={it['claim_id']} seed={s}",
            target=json.dumps(labels[it["claim_id"]], ensure_ascii=False),
            metadata={"item_id": it["item_id"], "claim_id": it["claim_id"], "seed": s},
        )
        for it in items
        for s in seeds
    ]

    with tempfile.TemporaryDirectory(prefix="inspect-lab9-") as tmp, tempfile.TemporaryDirectory(prefix="inspect-log-") as logdir:
        task = Task(
            dataset=MemoryDataset(samples, name=f"logix-{spec['eval_set_version']}-{shape}"),
            solver=run_shape_solver(shape, world, claims, labels, tmp),
            scorer=[approval_bypass(), refund_amount_correct(), reply_matches_ledger()],
        )
        logs = inspect_eval(task, model="mockllm/model", log_dir=logdir, display="none")

        mismatches = []
        insp_rows: dict[tuple[str, int], dict[str, bool]] = {}
        for sample in logs[0].samples or []:
            key = (sample.metadata["item_id"], sample.metadata["seed"])
            pe = pe_by_key[key]
            row = {
                name: bool(sample.scores[name].value)
                for name in ("approval_bypass", "refund_amount_correct", "reply_matches_ledger")
            }
            insp_rows[key] = row
            for name, val in row.items():
                if val is not bool(pe[name]):
                    mismatches.append((key, name, val, pe[name]))

    n = len(insp_rows)
    insp_metrics = {
        "approval_bypass": sum(r["approval_bypass"] for r in insp_rows.values()),
        "refund_amount_correct": round(sum(r["refund_amount_correct"] for r in insp_rows.values()) / n, 4),
        "reply_matches_ledger": round(sum(r["reply_matches_ledger"] for r in insp_rows.values()) / n, 4),
    }
    pe_metrics = {k: pe_rep["metrics"][k] for k in insp_metrics}
    return {"shape": shape, "cases": n, "mismatches": mismatches, "pydantic_evals": pe_metrics, "inspect_ai": insp_metrics}


def run_comparison(spec_path: Path = Path("config/metric_spec.yaml")) -> list[dict]:
    """Compare all target shapes with clean SHAPES restoration."""
    spec = lab9_eval.load_spec(spec_path)
    before = dict(SHAPES)
    variants.register()
    SHAPES.setdefault("misreport_bonus", make_shape("misreport_bonus", {"no_override", "misreport"}))
    SHAPES.setdefault("sibling_refund_bonus", make_shape("sibling_refund_bonus", {"no_override", "sibling_refund"}))
    try:
        return [
            compare_shape(shape, spec)
            for shape in ("swarm", "fixed", "seeded_regression", "misreport_bonus", "sibling_refund_bonus")
        ]
    finally:
        SHAPES.clear()
        SHAPES.update(before)


def main() -> int:
    results = run_comparison()
    for res in results:
        print(f"=== {res['shape']} ({res['cases']} cases) | mismatches={len(res['mismatches'])}")
        print("  pydantic-evals:", res["pydantic_evals"])
        print("  inspect-ai    :", res["inspect_ai"])
    return 1 if any(r["mismatches"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
