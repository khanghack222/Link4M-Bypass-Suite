#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ PROCESS-LEVEL BYPASS FAÇADE FOR JS FACES ⚡

    python -m src.bypass_api --url <url> [--engine KEY] [--headless] [--json]
    python -m src.bypass_api --list

This is the only command ``src/ui/menu.js``, ``bot_discord.js`` and
``service/worker.py`` shell out to. Engine log lines pass through untouched so
``formatLogLine()`` keeps matching them; this module adds the result card and
one canonical ``FINAL DESTINATION URL:`` line, plus an optional
``__BYPASS_JSON__{...}`` line for machine consumers.
"""

import argparse
import json
import os
import signal
import sys
from typing import Optional

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_SRC_DIR, ".."))
_CORE_DIR = os.path.join(_SRC_DIR, "core")
for _p in (_CORE_DIR, _SRC_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import runner_registry  # noqa: E402
from provider_table import PROVIDER_TABLE  # noqa: E402
from base_runner import BypassResult  # noqa: E402

DEFAULT_TIMEOUT = 480


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m src.bypass_api",
        description="Link4M Bypass Suite — unified provider dispatch",
    )
    ap.add_argument("url", nargs="?", default=None, help="target shortlink URL")
    ap.add_argument("--url", "-u", dest="url_opt", default=None, help="target shortlink URL")
    ap.add_argument("--engine", "-e", default=None, help="force engine key (see --list)")
    ap.add_argument("--headless", "-hl", action="store_true", default=True,
                    help="headless browser (default)")
    ap.add_argument("--head", "-w", action="store_true", help="visible browser window")
    ap.add_argument("--json", action="store_true", help="emit __BYPASS_JSON__ line")
    ap.add_argument("--list", action="store_true", help="print supported providers as JSON")
    ap.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT,
                    help=f"engine budget in seconds (default {DEFAULT_TIMEOUT})")
    return ap


def list_payload() -> dict:
    return {
        "supported": runner_registry.supported(),
        "engines": {spec.key: spec.module for spec in PROVIDER_TABLE},
        "providers": [
            {
                "key": spec.key,
                "kind": spec.kind.value,
                "hosts": list(spec.hosts),
                "module": spec.module,
                "note": spec.note,
                "ready": spec.ready,
            }
            for spec in PROVIDER_TABLE
        ],
    }


def run_once(url: str, engine: Optional[str] = None, headless: bool = True,
             timeout: int = DEFAULT_TIMEOUT) -> BypassResult:
    resolved = runner_registry.normalize_key(engine) if engine else runner_registry.classify(url)
    # Same default as runners.Link4MRunner: CDP unless L4M_ENGINE=legacy.
    use_cdp = (resolved == "LINK4M"
               and os.environ.get("L4M_ENGINE", "cdp").strip().lower() != "legacy")
    if use_cdp:
        try:
            from link4m_engine import ensure_chrome  # noqa: WPS433
            ensure_chrome()
        except Exception as exc:
            return BypassResult(
                success=False,
                engine="LINK4M",
                provider="LINK4M",
                error_code="ERR_BROWSER_CRASH",
                error_message=f"Chrome CDP không sẵn sàng: {exc}",
                metadata={"timeout": timeout, "headless": headless},
                stage="pre_flight",
            )
    res = _execute_with_headless(url, engine, headless, timeout=timeout)
    res.metadata.setdefault("timeout", timeout)
    return res


def _execute_with_headless(url: str, engine: Optional[str], headless: bool,
                            timeout: Optional[int] = None) -> BypassResult:
    """Xuất `L4M_HEADLESS` cho engine rồi khôi phục biến cũ.

    `headless` là tham số của façade, nhưng engine đọc cờ này từ môi trường
    (`link4m_engine` dùng nó để bật `--headless=new` và để biết có người ngồi
    trước màn hình hay không). Trước đây tham số bị bỏ qua hoàn toàn, nên job
    "headless" vẫn chạy Chrome có cửa sổ và vẫn chờ index lưới ảnh thủ công.
    """
    previous = os.environ.get("L4M_HEADLESS")
    os.environ["L4M_HEADLESS"] = "1" if headless else "0"
    try:
        return runner_registry.execute(url, engine=engine, headless=headless, timeout=timeout)
    finally:
        if previous is None:
            os.environ.pop("L4M_HEADLESS", None)
        else:
            os.environ["L4M_HEADLESS"] = previous


def emit_result(res: BypassResult, as_json: bool) -> int:
    if res.success and res.destination_url:
        try:
            from config import log_result_card  # noqa: WPS433
            log_result_card(res.destination_url, res.provider or res.engine)
        except Exception:
            pass
        print(f"FINAL DESTINATION URL: {res.destination_url}", flush=True)
        rc = 0
    else:
        print(f"[ERROR] {res.error_code or 'ERR_UNKNOWN'}: "
              f"{res.error_message or 'bypass failed'}", flush=True)
        rc = 1
    if as_json:
        print("__BYPASS_JSON__" + json.dumps(res.to_dict(), ensure_ascii=False), flush=True)
    return rc


def _reap_descendants() -> None:
    """Thu gom các tiến trình con / cháu (Playwright, Chrome, node) của PID hiện tại khi timeout."""
    cur_pid = os.getpid()
    protected_pids = {3856, 3914, cur_pid}
    try:
        import psutil
        parent = psutil.Process(cur_pid)
        children = parent.children(recursive=True)
        for child in children:
            if child.pid not in protected_pids:
                try:
                    child.terminate()
                except Exception:
                    pass
        _, alive = psutil.wait_procs(children, timeout=1.0)
        for child in alive:
            if child.pid not in protected_pids:
                try:
                    child.kill()
                except Exception:
                    pass
        return
    except Exception:
        pass

    # Fallback qua /proc nếu psutil không có sẵn
    try:
        child_pids = []
        for path_c in (f"/proc/{cur_pid}/task/{cur_pid}/children", f"/proc/{cur_pid}/children"):
            if os.path.exists(path_c):
                try:
                    with open(path_c, "r", encoding="utf-8") as f:
                        child_pids = [int(p) for p in f.read().split() if p.isdigit()]
                    break
                except Exception:
                    pass
        for cpid in child_pids:
            if cpid not in protected_pids:
                try:
                    os.kill(cpid, signal.SIGKILL)
                except Exception:
                    pass
    except Exception:
        pass


def _arm_deadline(seconds: int, target: str, as_json: bool):
    """Đồng hồ cứng cho cả lượt chạy: hết giờ thì in envelope rồi thoát.

    ``--timeout`` trước đây chỉ là metadata. Khi Chrome chết giữa lúc driver
    đang chờ một lệnh (evaluate trên tab đã đóng), Playwright không có timeout
    cho lệnh đó và tiến trình treo vô hạn — đã thấy job chạy 850s rồi bị
    ``timeout`` ngoài giết mà không in kết quả nào. Timer này bảo đảm consumer
    luôn nhận được dòng ``__BYPASS_JSON__`` với ``ERR_TIMEOUT``.
    """
    import threading

    def fire() -> None:
        res = BypassResult(
            success=False,
            engine="",
            provider="",
            error_code="ERR_TIMEOUT",
            error_message=(f"engine vượt ngân sách {seconds}s — driver không trả về "
                           f"(Chrome chết giữa lệnh?)"),
            metadata={"url": target, "timeout": seconds, "deadline_hit": True},
            stage="deadline",
        )
        try:
            emit_result(res, as_json)
        except Exception:
            pass
        _reap_descendants()
        os._exit(1)

    timer = threading.Timer(seconds, fire)
    timer.daemon = True
    timer.start()
    return timer


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        print(json.dumps(list_payload(), ensure_ascii=False, indent=2))
        return 0

    target = args.url_opt or args.url
    if not target:
        print("[ERROR] ERR_PROVIDER_UNKNOWN: missing --url", flush=True)
        return 2

    headless = False if args.head else bool(args.headless)
    as_json = bool(args.json) or os.environ.get("BYPASS_API_JSON", "") == "1"
    budget = max(5, int(args.timeout or DEFAULT_TIMEOUT))
    # +20s để engine tự kết thúc gọn trước khi đồng hồ cứng nổ.
    timer = _arm_deadline(budget + 20, target, as_json)
    try:
        res = run_once(target, engine=args.engine, headless=headless, timeout=budget)
    finally:
        timer.cancel()
    return emit_result(res, as_json)


if __name__ == "__main__":
    sys.exit(main())
