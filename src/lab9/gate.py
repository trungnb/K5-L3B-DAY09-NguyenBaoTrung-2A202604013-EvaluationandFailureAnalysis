"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def _finite_num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    problems: list[str] = []
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return problems
    new_m = {m["id"]: m for m in spec.get("metrics") or []}
    for bm in base_spec.get("metrics") or []:
        mid = bm["id"]
        if mid not in new_m:
            problems.append(f"ratchet: metric {mid} removed")
            continue
        nm = new_m[mid]
        if bm.get("blocking") and not nm.get("blocking"):
            problems.append(f"ratchet: metric {mid} made non-blocking")
        bth, nth = bm.get("threshold") or {}, nm.get("threshold") or {}
        if "max" in bth and (not _finite_num(nth.get("max")) or nth["max"] > bth["max"]):
            problems.append(f"ratchet: metric {mid} max loosened")
        if "min" in bth and (not _finite_num(nth.get("min")) or nth["min"] < bth["min"]):
            problems.append(f"ratchet: metric {mid} min loosened")
        if "max_increase" in bth and (not _finite_num(nth.get("max_increase")) or nth["max_increase"] > bth["max_increase"]):
            problems.append(f"ratchet: metric {mid} max_increase loosened")
        if bth.get("no_significant_drop") and not nth.get("no_significant_drop"):
            problems.append(f"ratchet: metric {mid} dropped no_significant_drop")
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        sk = (bs["name"], bs["metric"])
        if sk not in new_s:
            problems.append(f"ratchet: slice {sk[0]}/{sk[1]} removed")
            continue
        ns = new_s[sk]
        if bs.get("blocking") and not ns.get("blocking"):
            problems.append(f"ratchet: slice {sk[0]}/{sk[1]} made non-blocking")
        if "min" in bs and (not _finite_num(ns.get("min")) or ns["min"] < bs["min"]):
            problems.append(f"ratchet: slice {sk[0]}/{sk[1]} min loosened")
        if "max" in bs and (not _finite_num(ns.get("max")) or ns["max"] > bs["max"]):
            problems.append(f"ratchet: slice {sk[0]}/{sk[1]} max loosened")
        if bs.get("no_significant_drop") and not ns.get("no_significant_drop"):
            problems.append(f"ratchet: slice {sk[0]}/{sk[1]} dropped no_significant_drop")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []
    pr_metrics = pr.get("metrics") or {}
    for k, v in pr_metrics.items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"non-finite metric {k}={v}")
    for m in spec.get("metrics") or []:
        mid = m["id"]
        if mid in (base.get("metrics") or {}) and pr_metrics.get(mid) is None:
            problems.append(f"metric {mid} is None")
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s)")
    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    manifest = pr.get("manifest") or {}
    want_len = int(manifest.get("items", 0)) * len(manifest.get("seeds") or [])
    if len(pr_rows) != want_len:
        problems.append(f"row count {len(pr_rows)} != manifest {want_len}")
    if len(pr_rows) != len(base_rows):
        problems.append(f"row count {len(pr_rows)} != baseline {len(base_rows)}")
    pr_keys = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    base_keys = [(r.get("item_id"), r.get("seed")) for r in base_rows]
    if len(pr_keys) != len(set(pr_keys)):
        problems.append("duplicate (item_id, seed) rows")
    if set(pr_keys) != set(base_keys):
        problems.append("(item_id, seed) set differs from baseline")
    row_metrics = {m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS}
    row_metrics |= {s["metric"] for s in spec.get("slices") or [] if s.get("metric") in GRADERS}
    if base_rows:
        row_metrics |= {m["id"] for m in spec.get("metrics") or [] if m["id"] in base_rows[0]}
        row_metrics |= {s["metric"] for s in spec.get("slices") or [] if s.get("metric") in base_rows[0]}
    base_slices = {(r.get("item_id"), r.get("seed")): sorted(r.get("slices") or []) for r in base_rows}
    row_error = False
    for r in pr_rows:
        key = (r.get("item_id"), r.get("seed"))
        for mid in sorted(row_metrics):
            val = r.get(mid)
            if val is None or (isinstance(val, float) and not math.isfinite(val)):
                problems.append(f"invalid row value {mid}={val!r} at {key[0]}@{key[1]}")
                row_error = True
                break
        if key in base_slices and sorted(r.get("slices") or []) != base_slices[key]:
            problems.append(f"slice tags differ from baseline at {key[0]}@{key[1]}")
    if pr_rows and not row_error:
        agg_ids = [mid for mid in sorted(row_metrics) if mid in pr_rows[0]]
        if agg_ids:
            has_cost = all(_finite_num(r.get("cost")) for r in pr_rows)
            if not has_cost and any("cost" in r for r in pr_rows):
                problems.append("non-finite or non-numeric row cost")
            agg_rows = pr_rows if has_cost else [{**r, "cost": 0.0} for r in pr_rows]
            try:
                recomputed = aggregate(agg_rows, agg_ids, k_values=spec.get("pass_k", []))
            except (TypeError, ValueError) as exc:
                problems.append(f"failed to aggregate rows: {exc}")
                recomputed = {}
            for mid, want in recomputed.items():
                if mid not in pr_metrics or want is None:
                    continue
                if mid == "cost_per_success" and not has_cost:
                    continue
                got = pr_metrics[mid]
                if not _finite_num(got) or abs(float(got) - float(want)) > 1e-4:
                    problems.append(f"metric {mid}={got!r} disagrees with rows ({want!r})")
    if base_spec is not None:
        problems.extend(_ratchet_problems(spec, base_spec))
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice."""
    bs = spec.get("bootstrap", {})
    blocked, lines = [], []
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        a = per_item(pr, mid, slice_name=name)
        b = per_item(base, mid, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "min" in s and val < s["min"]:
            verdict = "fail"
        elif "max" in s and val > s["max"]:
            verdict = "fail"
        if s.get("no_significant_drop") and val is not None:
            keys = sorted(set(a) & set(b))
            if not keys:
                verdict = "fail"
            else:
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys],
                    [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(f"slice:{name}/{mid}")
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: v for k, v in s.items() if k in ("min", "max", "no_significant_drop")}
        lines.append(f"  slice:{name}/{mid:<14} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
