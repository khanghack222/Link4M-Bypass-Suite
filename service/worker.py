# -*- coding: utf-8 -*-
"""Hàng đợi + worker chạy engine trong thread, tuần tự hoá để không nổ RAM.

Chrome dùng chung một profile nên các job PHẢI chạy nối tiếp (Engine đóng hết
tab khác khi mở). Vì vậy mặc định 1 worker; tăng ``WORKERS`` chỉ khi RAM dư.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import traceback
from typing import Optional

from .config import CFG, L4M_ENGINE, REPO

for _p in (os.path.join(REPO, "src", "core"), os.path.join(REPO, "src"), REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _blocking_bypass(alias: str, keep_open: bool = False) -> dict:
    """Chạy thật trong thread (blocking) — engine là sync."""
    from link4m_engine import bypass_alias  # noqa: WPS433
    return bypass_alias(alias, keep_open=keep_open)


def _registry_bypass(url: str, provider: str) -> dict:
    """Dispatch qua registry cho mọi provider không phải Link4M/CDP."""
    import runner_registry  # noqa: WPS433
    res = runner_registry.execute(url, engine=provider, headless=True)
    return {
        "ok": bool(res.success),
        "destination": res.destination_url or "",
        "stage": res.stage or "",
        "error": res.error_message or res.error_code or "",
    }


def _run_provider(job: dict) -> dict:
    """Một job = một lần dispatch. Link4M/CDP đi đường alias đã kiểm chứng."""
    provider = (job.get("provider") or "").lower()
    if provider == "link4m" and L4M_ENGINE == "cdp":
        return _blocking_bypass(job["key"])
    return _registry_bypass(job["url"], provider.upper())


class WorkerPool:
    def __init__(self, store, log):
        self.store = store
        self.log = log
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=CFG.MAX_QUEUE)
        self._waiters: dict[str, asyncio.Future] = {}
        self._tasks: list[asyncio.Task] = []
        self._inflight = 0

    # ------------------------------------------------------------- vòng đời
    async def start(self) -> None:
        self.store.requeue_running()
        # Chỉ cần Chrome khi Link4M chạy engine CDP; provider khác tự lo browser.
        if L4M_ENGINE == "cdp":
            try:
                from link4m_engine import ensure_chrome
                await asyncio.to_thread(ensure_chrome)
                self.log("Chrome CDP sẵn sàng (đi thẳng, không proxy)")
            except Exception as exc:  # pragma: no cover
                self.log(f"CẢNH BÁO: chưa bật được Chrome: {exc}")
        else:
            self.log(f"L4M_ENGINE={L4M_ENGINE}: bỏ qua Chrome CDP")
        for i in range(CFG.WORKERS):
            self._tasks.append(asyncio.create_task(self._worker(i)))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    # ---------------------------------------------------------------- submit
    @property
    def inflight(self) -> int:
        return self._inflight

    @property
    def queued(self) -> int:
        return self.queue.qsize()

    def submit(self, job_id: str) -> bool:
        if self.queue.full():
            return False
        self.queue.put_nowait(job_id)
        return True

    async def wait(self, job_id: str, timeout: float) -> Optional[dict]:
        fut = self._waiters.get(job_id)
        if fut is None:
            fut = asyncio.get_event_loop().create_future()
            self._waiters[job_id] = fut
        try:
            await asyncio.wait_for(asyncio.shield(fut), timeout)
        except asyncio.TimeoutError:
            pass
        return self.store.get_job(job_id)

    def _resolve(self, job_id: str, payload: dict) -> None:
        fut = self._waiters.pop(job_id, None)
        if fut and not fut.done():
            fut.set_result(payload)

    # ---------------------------------------------------------------- worker
    async def _worker(self, n: int) -> None:
        while True:
            job_id = await self.queue.get()
            self._inflight += 1
            try:
                await self._run_job(job_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                self.log(f"[worker{n}] lỗi không ngờ: {exc}")
                self.store.set_status(job_id, "error", error=str(exc)[:300])
                self._resolve(job_id, {"id": job_id, "status": "error"})
            finally:
                self._inflight -= 1
                self.queue.task_done()

    async def _run_job(self, job_id: str) -> None:
        job = self.store.get_job(job_id)
        if not job:
            return
        last_err = ""
        for attempt in range(1, CFG.MAX_TRIES + 1):
            self.store.incr_tries(job_id)
            self.store.set_status(job_id, "running")
            t0 = time.time()
            try:
                res = await asyncio.wait_for(
                    asyncio.to_thread(_run_provider, job),
                    timeout=CFG.JOB_TIMEOUT)
            except asyncio.TimeoutError:
                last_err = f"timeout sau {CFG.JOB_TIMEOUT}s"
                self.log(f"[job {job_id}] {last_err} (thử {attempt})")
                res = None
            except Exception as exc:
                last_err = str(exc)[:300]
                self.log(f"[job {job_id}] lỗi: {last_err}")
                res = None

            elapsed = round((time.time() - t0) * 1000, 1)
            if res and res.get("ok") and str(res.get("destination", "")).startswith("http"):
                dest = res["destination"]
                self.store.set_status(job_id, "success", destination=dest,
                                      elapsed_ms=elapsed, error=None)
                if CFG.CACHE_ENABLED:
                    self.store.cache_put(job["provider"], job["key"], dest)
                self.log(f"[job {job_id}] OK {elapsed}ms -> {dest[:70]}")
                self._resolve(job_id, {"id": job_id, "status": "success", "destination": dest})
                return

            last_err = last_err or (res or {}).get("stage", "không lấy được link đích")
            if attempt < CFG.MAX_TRIES:
                await asyncio.sleep(CFG.RETRY_DELAY)

        self.store.set_status(job_id, "error", error=last_err, elapsed_ms=elapsed)
        self.log(f"[job {job_id}] THUA: {last_err}")
        self._resolve(job_id, {"id": job_id, "status": "error", "error": last_err})
