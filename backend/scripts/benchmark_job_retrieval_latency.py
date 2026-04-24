#!/usr/bin/env python3
"""
Compare job-load latency: JOBS_RETRIEVAL_FILTER on vs off (same users= kwarg).

Usage (from repo root or backend/):
  cd backend && python scripts/benchmark_job_retrieval_latency.py --filter off
  cd backend && python scripts/benchmark_job_retrieval_latency.py --filter on

Or both in one shot:
  python scripts/benchmark_job_retrieval_latency.py --compare
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_first_user(users_path: Path) -> dict:
    with open(users_path, encoding="utf-8") as f:
        raw = json.load(f)
    u = raw[0]
    return {k: v for k, v in u.items() if not str(k).startswith("_")}


async def _run_bench(
    users: List[dict], warmup: int, repeat: int
) -> Tuple[List[Dict[str, Any]], List[float]]:
    # Imported after env is set by caller
    from app.database import get_all_jobs_with_timing

    for _ in range(warmup):
        await get_all_jobs_with_timing(users=users)

    metas: List[Dict[str, Any]] = []
    wall_ms: List[float] = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        _jobs, meta = await get_all_jobs_with_timing(users=users)
        wall_ms.append((time.perf_counter() - t0) * 1000.0)
        metas.append(meta)
    return metas, wall_ms


def _summarize(metas: List[dict], wall_ms: List[float]) -> dict:
    mongo = [m["mongo_ranked_find_ms"] for m in metas]
    pyb = [m["python_build_jobs_ms"] for m in metas]
    tot = [m["get_all_jobs_total_ms"] for m in metas]
    last = metas[-1]
    return {
        "wall_ms_mean": round(statistics.mean(wall_ms), 2),
        "wall_ms_stdev": round(statistics.stdev(wall_ms), 2) if len(wall_ms) > 1 else 0.0,
        "mongo_find_ms_mean": round(statistics.mean(mongo), 2),
        "python_build_ms_mean": round(statistics.mean(pyb), 2),
        "get_all_jobs_total_ms_mean": round(statistics.mean(tot), 2),
        "n_ranked_raw": last["n_ranked_raw"],
        "n_jobs": last["n_jobs"],
        "jobs_retrieval_filter_applied": bool(last.get("jobs_retrieval_filter_applied")),
    }


def main() -> int:
    backend = _backend_root()
    sys.path.insert(0, str(backend))

    ap = argparse.ArgumentParser(description="Benchmark get_all_jobs_with_timing")
    ap.add_argument("--filter", choices=["on", "off"], help="JOBS_RETRIEVAL_FILTER")
    ap.add_argument(
        "--users-json",
        type=Path,
        default=backend / "tests" / "test_users.json",
    )
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument(
        "--compare",
        action="store_true",
        help="Run filter off then on via subprocess and print comparison table",
    )
    args = ap.parse_args()

    if args.compare:
        return main_compare()

    if not args.filter:
        ap.error("--filter on|off required (or use --compare)")

    from dotenv import load_dotenv

    load_dotenv(backend / ".env")
    os.environ["JOBS_RETRIEVAL_FILTER"] = "1" if args.filter == "on" else "0"

    user = _load_first_user(args.users_json)
    users = [user]

    metas, wall = asyncio.run(_run_bench(users, args.warmup, args.repeat))
    out = {
        "JOBS_RETRIEVAL_FILTER": args.filter,
        "warmup": args.warmup,
        "repeat": args.repeat,
        **_summarize(metas, wall),
    }
    print(json.dumps(out, indent=2))
    return 0


def main_compare() -> int:
    backend = _backend_root()
    script = Path(__file__).resolve()
    py = sys.executable

    def run(mode: str) -> dict:
        r = subprocess.run(
            [
                py,
                "-u",
                str(script),
                "--warmup",
                "1",
                "--repeat",
                "3",
                "--filter",
                mode,
            ],
            cwd=str(backend),
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(backend)},
        )
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            raise SystemExit(r.returncode)
        return json.loads(r.stdout)

    off = run("off")
    on = run("on")

    print("Job retrieval latency (get_all_jobs_with_timing, first user from test_users.json)")
    print("=" * 72)
    print(f"{'Metric':<42} {'FILTER off':>14} {'FILTER on':>14}")
    print("-" * 72)
    rows = [
        ("mongo_ranked_find_ms (mean)", "mongo_find_ms_mean"),
        ("python_build_jobs_ms (mean)", "python_build_ms_mean"),
        ("get_all_jobs_total_ms (mean)", "get_all_jobs_total_ms_mean"),
        ("wall clock mean (ms)", "wall_ms_mean"),
        ("n_ranked_raw (last run)", "n_ranked_raw"),
        ("n_jobs built (last run)", "n_jobs"),
        ("jobs_retrieval_filter_applied", "jobs_retrieval_filter_applied"),
    ]
    for label, key in rows:
        a, b = off.get(key), on.get(key)
        print(f"{label:<42} {str(a):>14} {str(b):>14}")
    print("-" * 72)
    mf_off, mf_on = off["mongo_find_ms_mean"], on["mongo_find_ms_mean"]
    if mf_off > 0 and mf_on >= 0:
        pct = 100.0 * mf_on / mf_off
        print(
            f"Mongo find (mean): filter-on is {pct:.1f}% of filter-off "
            f"({'faster' if mf_on < mf_off else 'slower or equal'} when lower is better)."
        )
    print(
        "\nNote: Mongo latency varies with cold/warm cache and server load; "
        "when filter-on returns the same n_ranked_raw as filter-off, every "
        "active job matched the location OR for this user (common on a small, "
        "geo-focused corpus). The cap (JOBS_RETRIEVAL_LIMIT) matters on larger N."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
