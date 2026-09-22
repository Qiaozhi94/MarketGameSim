"""ADR-015: prove that a code change leaves frozen evidence economically identical.

Usage (from the repository root, with this tree's ``src`` importable)::

    python tools/prove_economic_equivalence.py --baseline <git-ref> [--t215] [--h2] \
        [--out proof.json]

* ``--t215``: re-executes every 0.1.5 T215 block with the current tree and compares
  the economic projection of each primary run with the events stored in the
  frozen checkpoints (``artifacts/formal/T215/checkpoints``).
* ``--h2``: the 0.3.1 H2 index stores only digests, so the baseline must be
  re-run.  The baseline ref is checked out into a temporary worktree and run
  there; it must reproduce every frozen ``events_sha256`` exactly, otherwise the
  proof is void (the baseline would not be the code that produced the evidence).

Both sides load :mod:`market_game_sim.evidence.economic_projection` from *this*
tree by file path, so the baseline does not need to contain the module and both
sides are projected by the same definition.  Exit status is 0 only when every
compared run is economically identical and every sanity check holds.
"""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROJECTION_PATH = ROOT / "src" / "market_game_sim" / "evidence" / "economic_projection.py"
H2_INDEX = ROOT / "docs" / "experiments" / "H2-ai-evidence-index.json"
T215_CHECKPOINTS = ROOT / "artifacts" / "formal" / "T215" / "checkpoints"


def _load_projection():
    spec = importlib.util.spec_from_file_location("_economic_projection", PROJECTION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare(baseline: dict[str, str], current: dict[str, str]) -> dict[str, object]:
    """Pure comparison of two ``{run_key: economic_digest}`` maps."""
    keys = sorted(set(baseline) | set(current))
    differing = [k for k in keys if baseline.get(k) != current.get(k)]
    return {"compared": len(keys), "identical": len(keys) - len(differing), "differing": differing}


# --------------------------------------------------------------------------- #
# H2 (runs inside whichever tree is on sys.path)
# --------------------------------------------------------------------------- #


def dump_h2(out_path: pathlib.Path) -> None:
    from market_game_sim.experiment.h2 import runner
    from market_game_sim.experiment.h2.analysis import canonical_digest

    projection = _load_projection()
    index = json.loads(H2_INDEX.read_text(encoding="utf-8"))
    digests: dict[str, str] = {}
    frozen_matches = 0
    for entry in index["included"]:
        block = runner.run_ai_block(int(entry["seed"]))
        for run in block.runs:
            events = json.loads(json.dumps(run.result.events, default=str))
            digests[f"{entry['order_index']}:{run.arm}"] = projection.economic_digest(events)
            frozen_matches += (
                canonical_digest(run.result.events) == entry["arms"][run.arm]["events_sha256"]
            )
    out_path.write_text(
        json.dumps({"digests": digests, "frozen_full_digest_matches": frozen_matches}),
        encoding="utf-8",
    )


def _run_dump(src: pathlib.Path, out: pathlib.Path) -> dict:
    env = {**os.environ, "PYTHONPATH": str(src)}
    subprocess.run(
        [sys.executable, str(pathlib.Path(__file__).resolve()), "--dump-h2", str(out)],
        check=True,
        cwd=ROOT,
        env=env,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def prove_h2(baseline_ref: str) -> dict[str, object]:
    arms = sum(len(e["arms"]) for e in json.loads(H2_INDEX.read_text("utf-8"))["included"])
    with tempfile.TemporaryDirectory() as tmp:
        tree = pathlib.Path(tmp) / "baseline"
        subprocess.run(
            ["git", "worktree", "add", "--detach", "-q", str(tree), baseline_ref],
            check=True,
            cwd=ROOT,
        )
        try:
            base = _run_dump(tree / "src", pathlib.Path(tmp) / "base.json")
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=ROOT)
        cur = _run_dump(ROOT / "src", pathlib.Path(tmp) / "cur.json")
    result = compare(base["digests"], cur["digests"])
    result["baseline_reproduces_frozen_index"] = base["frozen_full_digest_matches"] == arms
    result["current_full_digest_matches_frozen"] = cur["frozen_full_digest_matches"]
    return result


# --------------------------------------------------------------------------- #
# T215 (baseline = the events stored in the frozen checkpoints)
# --------------------------------------------------------------------------- #


def prove_t215() -> dict[str, object]:
    from market_game_sim.experiment.factorial import load_factorial_plan
    from market_game_sim.showcase.formal import DEFAULT_PLAN, _execute_block

    projection = _load_projection()
    binding = load_factorial_plan(DEFAULT_PLAN)
    base: dict[str, str] = {}
    cur: dict[str, str] = {}
    outcome_fields_differ: list[str] = []
    for path in sorted(T215_CHECKPOINTS.glob("seed-*.json.gz")):
        with gzip.open(path) as fh:
            body = json.loads(fh.read())["body"]
        seed = int(body["seed"])
        results, _, _ = _execute_block(seed, binding)
        for model, cells in results.items():
            for cell, run in cells.items():
                key = f"{seed}:{model}:{cell}"
                frozen = body["primary_runs"][model][cell]
                base[key] = projection.economic_digest(frozen["events"])
                events = json.loads(json.dumps(run.events, default=str))
                cur[key] = projection.economic_digest(events)
                outcome = {
                    "terminated": run.terminated,
                    "abort_code": run.abort_code,
                    "book_last_ticks": run.book_last_ticks,
                    "classification": json.loads(
                        json.dumps(dataclasses.asdict(run.classification))
                    ),
                }
                if any(frozen[k] != v for k, v in outcome.items()):
                    outcome_fields_differ.append(key)
    result = compare(base, cur)
    result["outcome_fields_differ"] = outcome_fields_differ
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", help="git ref of the code that produced the evidence")
    parser.add_argument("--t215", action="store_true")
    parser.add_argument("--h2", action="store_true")
    parser.add_argument("--out")
    parser.add_argument("--dump-h2", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.dump_h2:
        dump_h2(pathlib.Path(args.dump_h2))
        return 0

    projection = _load_projection()
    proof: dict[str, object] = {
        "projection": (
            f"market_game_sim.evidence.economic_projection v{projection.PROJECTION_VERSION}"
        ),
        "baseline_ref": args.baseline,
    }
    ok = True
    if args.t215:
        t215 = prove_t215()
        proof["t215"] = t215
        ok &= t215["identical"] == t215["compared"] and not t215["outcome_fields_differ"]
    if args.h2:
        if not args.baseline:
            parser.error("--h2 needs --baseline")
        h2 = prove_h2(args.baseline)
        proof["h2"] = h2
        ok &= h2["identical"] == h2["compared"] and bool(h2["baseline_reproduces_frozen_index"])
    proof["economically_identical"] = ok
    text = json.dumps(proof, indent=2, sort_keys=True)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
