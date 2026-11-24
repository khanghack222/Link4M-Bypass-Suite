#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Benchmark Link4M Bypass Suite — đo latency từng đường.

Chạy:  .venv/bin/python tools/benchmark.py [--url URL] [--n N] [--cold]

Đường đo:
  [1] /health                    overhead HTTP thuần (FastAPI + uvicorn)
  [2] /api/v1/bypass (cache hit) đường nhanh nhất khi alias đã có trong cache
  [3] src/core/link4m_http.py    HTTP-only, không Chrome (mở + advertise)
  [4] cold bypass (Chrome)       chỉ đọc từ DB các job đã chạy; --cold để chạy thật
"""
from __future__ import annotations

import argparse
import json
import statistics
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8080"
DEFAULT_TARGET = "https://link4m.net/go/2kCcIqn"


def _get(path: str, timeout: float = 40.0) -> tuple[float, str]:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "benchmark/1.0"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
    return (time.perf_counter() - t0) * 1000.0, body


def _pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(p / 100.0 * (len(ordered) - 1))))
    return ordered[idx]


def _stats(label: str, samples: list[float]) -> str:
    if not samples:
        return f"{label:<22} không có mẫu"
    return (
        f"{label:<22} n={len(samples):<3} "
        f"min={min(samples):7.1f}ms  "
        f"median={statistics.median(samples):7.1f}ms  "
        f"p95={_pct(samples, 95):7.1f}ms  "
        f"max={max(samples):7.1f}ms"
    )


def bench_health(n: int) -> list[float]:
    samples: list[float] = []
    for _ in range(n):
        try:
            ms, _ = _get("/health", 5)
            samples.append(ms)
        except urllib.error.URLError as exc:
            print(f"  /health lỗi: {exc}")
            break
    return samples


def bench_cache(n: int, target: str) -> list[float]:
    samples: list[float] = []
    path = "/api/v1/bypass?url=" + urllib.parse.quote(target, safe="") + "&wait=1"
    for _ in range(n):
        try:
            ms, body = _get(path, 40)
            data = json.loads(body)
            if data.get("status") != "success":
                print(f"  cache miss: {data.get('status')} — dừng đo")
                break
            samples.append(ms)
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"  cache lỗi: {exc}")
            break
    return samples


def bench_stats() -> dict:
    try:
        ms, body = _get("/api/v1/stats", 5)
        data = json.loads(body)
        data["_latency_ms"] = round(ms, 1)
        return data
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}


def bench_http_only(alias: str, n: int) -> list[float]:
    """Đường HTTP thuần: mở alias + POST get-advertise, không Chrome."""
    script = ROOT / "src" / "core" / "link4m_http.py"
    py = ROOT / ".venv" / "bin" / "python"
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        proc = subprocess.run(
            [str(py), str(script), alias],
            capture_output=True, text=True, timeout=90, cwd=str(ROOT),
        )
        dt = (time.perf_counter() - t0) * 1000.0
        if proc.returncode != 0 or '"alias"' not in proc.stdout:
            print(f"  http-only lỗi: {proc.stderr.strip()[:200]}")
            break
        samples.append(dt)
    return samples


def cold_runs_from_db() -> list[dict]:
    db = ROOT / "data" / "service.db"
    if not db.exists():
        return []
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT elapsed_ms, tries, destination, updated FROM jobs "
            "WHERE status='success' ORDER BY updated DESC LIMIT 20"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return [dict(r) for r in rows]


def run_cold_bypass(target: str, timeout: float) -> tuple[float, str]:
    """Chạy thật một lần bypass qua service, không dùng cache (bypass_cache=1)."""
    path = "/api/v1/bypass?url=" + urllib.parse.quote(target, safe="") + "&wait=1&bypass_cache=1"
    t0 = time.perf_counter()
    try:
        _, body = _get(path, timeout)
    except urllib.error.URLError as exc:
        return (time.perf_counter() - t0) * 1000.0, f"lỗi: {exc}"
    dt = (time.perf_counter() - t0) * 1000.0
    try:
        data = json.loads(body)
        return dt, f"{data.get('status')} | {str(data.get('destination_url'))[:70]}"
    except json.JSONDecodeError:
        return dt, body[:120]


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark Link4M Bypass Suite")
    ap.add_argument("--url", default=DEFAULT_TARGET, help="link4m URL để test")
    ap.add_argument("--n", type=int, default=20, help="số lần lặp mỗi phép đo")
    ap.add_argument("--cold", action="store_true", help="chạy thật một cold bypass (tốn ~200s)")
    ap.add_argument("--timeout", type=float, default=280.0, help="timeout cho cold bypass (giây)")
    args = ap.parse_args()

    alias = args.url.rstrip("/").rsplit("/", 1)[-1]
    print("=== BENCHMARK LINK4M BYPASS SUITE ===")
    print(f"target: {args.url}   alias: {alias}")
    print()

    health = bench_health(args.n)
    print("[1] " + _stats("/health", health))

    cache = bench_cache(args.n, args.url)
    print("[2] " + _stats("cache hit", cache))

    stats = bench_stats()
    print(f"[3] /api/v1/stats     {stats.pop('_latency_ms', '?')}ms  {json.dumps(stats, ensure_ascii=False)}")

    http_only = bench_http_only(alias, min(args.n, 5))
    print("[4] " + _stats("http-only (no Chrome)", http_only))

    cold = cold_runs_from_db()
    print(f"[5] cold bypass — {len(cold)} job đã ghi trong DB")
    if cold:
        times = [c["elapsed_ms"] for c in cold]
        print(f"    min={min(times)/1000:.1f}s  median={statistics.median(times)/1000:.1f}s  max={max(times)/1000:.1f}s")
        for c in cold[:5]:
            print(f"    {c['elapsed_ms']/1000:7.1f}s  tries={c['tries']}  {str(c['destination'])[:60]}")
    print()

    if args.cold:
        print("[6] cold bypass thật (Chrome + sponsor + captcha)…")
        ms, info = run_cold_bypass(args.url, args.timeout)
        print(f"    {ms/1000:.1f}s  {info}")
        print()

    print("=== KẾT LUẬN ===")
    if cache:
        print(f"cache hit   : {statistics.median(cache):.1f}ms   (đường nhanh nhất)")
    if http_only:
        print(f"http-only   : {statistics.median(http_only)/1000:.2f}s   (bỏ Chrome, chỉ tới bước captcha)")
    if cold:
        print(f"cold bypass : {statistics.median([c['elapsed_ms'] for c in cold])/1000:.1f}s   (Chrome + sponsor + captcha)")
    if health:
        print(f"overhead    : {statistics.median(health):.1f}ms   (HTTP thuần)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
