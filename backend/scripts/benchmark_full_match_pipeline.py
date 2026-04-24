#!/usr/bin/env python3
"""
End-to-end pipeline (like POST /match for one user):
  asyncio.gather(get_all_jobs_with_timing(users=[u]), get_all_occupations_with_timing())
  then asyncio.to_thread(match_user_with_data, u, jobs, occ)

Compare latency with JOBS_RETRIEVAL_FILTER on vs off (subprocesses for clean env).
Compare projection: ``--compare-projection`` (retrieval filter ON, projection ON vs OFF).

Usage:
  cd backend && python scripts/benchmark_full_match_pipeline.py --filter on
  cd backend && python scripts/benchmark_full_match_pipeline.py --compare
  cd backend && python scripts/benchmark_full_match_pipeline.py --compare-projection
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
from typing import Any, Dict, List


def _backend() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_user(users_path: Path, index: int) -> dict:
    with open(users_path, encoding="utf-8") as f:
        raw = json.load(f)[index]
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


async def _run_pipeline_once(user: dict) -> Dict[str, Any]:
    from app.database import get_all_jobs_with_timing, get_all_occupations_with_timing
    from app.services.matching_service import match_user_with_data

    t0 = time.perf_counter()
    (jobs, jm), (occ, om) = await asyncio.gather(
        get_all_jobs_with_timing(users=[user]),
        get_all_occupations_with_timing(),
    )
    fetch_wall_ms = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    out = await asyncio.to_thread(match_user_with_data, user, jobs, occ)
    match_wall_ms = (time.perf_counter() - t1) * 1000.0

    return {
        "fetch_parallel_wall_ms": round(fetch_wall_ms, 2),
        "match_thread_pool_wall_ms": round(match_wall_ms, 2),
        "end_to_end_wall_ms": round(fetch_wall_ms + match_wall_ms, 2),
        "mongo_ranked_find_ms": round(float(jm.get("mongo_ranked_find_ms", 0)), 2),
        "python_build_jobs_ms": round(float(jm.get("python_build_jobs_ms", 0)), 2),
        "jobs_retrieval_filter_applied": jm.get("jobs_retrieval_filter_applied"),
        "jobs_find_use_projection": jm.get("jobs_find_use_projection"),
        "n_jobs": len(jobs),
        "n_occ": len(occ),
        "n_opp_recs": len(out.get("opportunity_recommendations", [])),
        "n_occ_recs": len(out.get("occupation_recommendations", [])),
        "occ_cache_hit": om.get("occupation_cache_hit"),
    }


async def _bench(user: dict, warmup: int, repeat: int) -> List[Dict[str, Any]]:
    for _ in range(warmup):
        await _run_pipeline_once(user)
    return [await _run_pipeline_once(user) for _ in range(repeat)]


def _mean(rows: List[Dict[str, Any]], key: str) -> float:
    vals = [r[key] for r in rows if key in r and isinstance(r[key], (int, float))]
    return round(statistics.mean(vals), 2) if vals else 0.0


def main() -> int:
    b = _backend()
    if str(b) not in sys.path:
        sys.path.insert(0, str(b))
    ap = argparse.ArgumentParser(description="Benchmark full match pipeline")
    ap.add_argument("--filter", choices=["on", "off"])
    ap.add_argument(
        "--projection",
        choices=["on", "off"],
        default=None,
        help="JOBS_FIND_USE_PROJECTION (default: use value from .env if omitted)",
    )
    ap.add_argument("--compare", action="store_true")
    ap.add_argument(
        "--compare-projection",
        action="store_true",
        help="JOBS_RETRIEVAL_FILTER on: compare projection on vs off (subprocesses)",
    )
    ap.add_argument("--users-json", type=Path, default=b / "tests" / "test_users.json")
    ap.add_argument("--user-index", type=int, default=0)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--repeat", type=int, default=2)
    args = ap.parse_args()

    if args.compare_projection:
        return _main_compare_projection(args)
    if args.compare:
        return _main_compare(args)

    if not args.filter:
        ap.error("--filter on|off required, or use --compare / --compare-projection")

    from dotenv import load_dotenv

    load_dotenv(b / ".env")
    os.environ["JOBS_RETRIEVAL_FILTER"] = "1" if args.filter == "on" else "0"
    if args.projection is not None:
        os.environ["JOBS_FIND_USE_PROJECTION"] = "1" if args.projection == "on" else "0"

    user = _load_user(args.users_json, args.user_index)
    rows = asyncio.run(_bench(user, args.warmup, args.repeat))
    last = rows[-1]

    out: Dict[str, Any] = {
        "JOBS_RETRIEVAL_FILTER": args.filter,
        "JOBS_FIND_USE_PROJECTION": args.projection or "(from .env)",
        "user_index": args.user_index,
        "user_id": user.get("user_id"),
        "warmup": args.warmup,
        "repeat": args.repeat,
        "mean_fetch_parallel_wall_ms": _mean(rows, "fetch_parallel_wall_ms"),
        "mean_match_thread_pool_wall_ms": _mean(rows, "match_thread_pool_wall_ms"),
        "mean_end_to_end_wall_ms": _mean(rows, "end_to_end_wall_ms"),
        "mean_mongo_ranked_find_ms": _mean(rows, "mongo_ranked_find_ms"),
        "mean_python_build_jobs_ms": _mean(rows, "python_build_jobs_ms"),
        "last_run": last,
    }
    print(json.dumps(out, indent=2))
    return 0


def _main_compare(args: argparse.Namespace) -> int:
    b = _backend()
    py = sys.executable
    script = Path(__file__).resolve()

    def run(mode: str, projection: str | None = None) -> dict:
        cmd = [
            py,
            "-u",
            str(script),
            "--filter",
            mode,
            "--warmup",
            str(args.warmup),
            "--repeat",
            str(args.repeat),
            "--user-index",
            str(args.user_index),
        ]
        if projection is not None:
            cmd.extend(["--projection", projection])
        r = subprocess.run(
            cmd,
            cwd=str(b),
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(b)},
        )
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
            raise SystemExit(r.returncode)
        return json.loads(r.stdout)

    on = run("on")
    off = run("off")

    print("Full pipeline benchmark (JOBS_RETRIEVAL_FILTER on = Mongo prefilter ON, default you want to keep)")
    print("Pipeline: gather(jobs, occupations) -> to_thread(match_user_with_data)")
    print("=" * 78)
    print(f"{'Metric (mean over repeats)':<46} {'FILTER on':>15} {'FILTER off':>15}")
    print("-" * 78)
    pairs = [
        ("fetch_parallel_wall_ms", "mean_fetch_parallel_wall_ms"),
        ("match_thread_pool_wall_ms", "mean_match_thread_pool_wall_ms"),
        ("end_to_end_wall_ms", "mean_end_to_end_wall_ms"),
        ("mongo_ranked_find_ms (jobs)", "mean_mongo_ranked_find_ms"),
        ("python_build_jobs_ms (jobs)", "mean_python_build_jobs_ms"),
    ]
    for label, key in pairs:
        print(f"{label:<46} {on.get(key, 0):>15.2f} {off.get(key, 0):>15.2f}")
    lo, lof = on["last_run"], off["last_run"]
    print("-" * 78)
    print(f"{'n_jobs (last run)':<46} {lo.get('n_jobs', ''):>15} {lof.get('n_jobs', ''):>15}")
    oon, ooff = f"{lo.get('n_opp_recs')}/{lo.get('n_occ_recs')}", f"{lof.get('n_opp_recs')}/{lof.get('n_occ_recs')}"
    print(f"{'n_opp_recs / n_occ_recs (last)':<46} {oon:>15} {ooff:>15}")
    e_on = on.get("mean_end_to_end_wall_ms", 0) or 0
    e_off = off.get("mean_end_to_end_wall_ms", 0) or 0
    if e_off > 0:
        print(
            f"\nEnd-to-end: ON is {100 * e_on / e_off:.1f}% of OFF wall time "
            f"({'less' if e_on < e_off else 'more'} work when lower is better)."
        )
    return 0


def _main_compare_projection(args: argparse.Namespace) -> int:
    b = _backend()
    py = sys.executable
    script = Path(__file__).resolve()

    def run(mode: str) -> dict:
        r = subprocess.run(
            [
                py,
                "-u",
                str(script),
                "--filter",
                "on",
                "--projection",
                mode,
                "--warmup",
                str(args.warmup),
                "--repeat",
                str(args.repeat),
                "--user-index",
                str(args.user_index),
            ],
            cwd=str(b),
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(b)},
        )
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
            raise SystemExit(r.returncode)
        return json.loads(r.stdout)

    on = run("on")
    off = run("off")

    print("Projection benchmark (JOBS_RETRIEVAL_FILTER=ON, same user; projection reduces BSON only)")
    print("Pipeline: gather(jobs, occupations) -> to_thread(match_user_with_data)")
    print("=" * 78)
    print(f"{'Metric (mean over repeats)':<46} {'PROJECTION on':>15} {'PROJECTION off':>15}")
    print("-" * 78)
    pairs = [
        ("fetch_parallel_wall_ms", "mean_fetch_parallel_wall_ms"),
        ("match_thread_pool_wall_ms", "mean_match_thread_pool_wall_ms"),
        ("end_to_end_wall_ms", "mean_end_to_end_wall_ms"),
        ("mongo_ranked_find_ms (jobs)", "mean_mongo_ranked_find_ms"),
        ("python_build_jobs_ms (jobs)", "mean_python_build_jobs_ms"),
    ]
    for label, key in pairs:
        print(f"{label:<46} {on.get(key, 0):>15.2f} {off.get(key, 0):>15.2f}")
    lo, lof = on["last_run"], off["last_run"]
    print("-" * 78)
    print(f"{'n_jobs (last run)':<46} {lo.get('n_jobs', ''):>15} {lof.get('n_jobs', ''):>15}")
    print(f"{'jobs_find_use_projection (last)':<46} {str(lo.get('jobs_find_use_projection')):>15} {str(lof.get('jobs_find_use_projection')):>15}")
    e_on = on.get("mean_end_to_end_wall_ms", 0) or 0
    e_off = off.get("mean_end_to_end_wall_ms", 0) or 0
    if e_off > 0:
        print(
            f"\nEnd-to-end: projection-ON is {100 * e_on / e_off:.1f}% of projection-OFF wall time "
            f"({'less' if e_on < e_off else 'more'} when lower is better)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
