#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ LINK4M BYPASS SUITE - UNIFIED AUTONOMOUS ENGINE ⚡
Auto-detects link type (GTraffic, Direct GTraffic, BBMKTS, LayMa, TrafficVN, Link4M)
and executes the appropriate bypass runner with zero manual intervention.
"""

import sys
import os
import time
import re
import argparse
import subprocess

# Configure UTF-8 for Windows Terminal
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(ROOT_DIR, "src", "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

DEST_FILE = os.path.join(ROOT_DIR, "destination_url.txt")
FINAL_DEST_FILE = os.path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt")

# ANSI Neon Palette for Windows Terminal
C_RESET = "\x1b[0m"
C_BOLD = "\x1b[1m"
C_DIM = "\x1b[2m"
C_CYAN = "\x1b[38;2;0;255;240m"
C_BLUE = "\x1b[38;2;30;144;255m"
C_PINK = "\x1b[38;2;255;20;147m"
C_BPINK = "\x1b[38;2;255;105;180m"
C_PURPLE = "\x1b[38;2;170;85;255m"
C_GREEN = "\x1b[38;2;0;255;150m"
C_YELLOW = "\x1b[38;2;255;235;59m"
C_ORANGE = "\x1b[38;2;255;140;0m"
C_RED = "\x1b[38;2;255;50;80m"
C_WHITE = "\x1b[38;2;255;255;255m"
C_GRAY = "\x1b[38;2;160;160;185m"

BG_CYAN = "\x1b[48;2;0;180;200m\x1b[38;2;0;0;0m\x1b[1m"
BG_PINK = "\x1b[48;2;255;20;147m\x1b[38;2;255;255;255m\x1b[1m"
BG_PURPLE = "\x1b[48;2;138;43;226m\x1b[38;2;255;255;255m\x1b[1m"
BG_GREEN = "\x1b[48;2;34;197;94m\x1b[38;2;0;0;0m\x1b[1m"
BG_YELLOW = "\x1b[48;2;250;204;21m\x1b[38;2;0;0;0m\x1b[1m"
BG_ORANGE = "\x1b[48;2;249;115;22m\x1b[38;2;255;255;255m\x1b[1m"
BG_RED = "\x1b[48;2;239;68;68m\x1b[38;2;255;255;255m\x1b[1m"
BG_BLUE = "\x1b[48;2;37;99;235m\x1b[38;2;255;255;255m\x1b[1m"


def print_banner():
    banner = [
        r"  ██████╗  ██╗   ██╗ █████╗  ██╗      ██████╗ ██╗   ██╗██████╗  █████╗ ███████╗███████╗",
        r"  ██╔══██╗ ██║   ██║██╔══██╗ ██║      ██╔══██╗╚██╗ ██╔╝██╔══██╗██╔══██╗██╔════╝██╔════╝",
        r"  ██║  ██║ ██║   ██║███████║ ██║      ██████╔╝ ╚████╔╝ ██████╔╝███████║███████╗███████╗",
        r"  ██║  ██║ ██║   ██║██╔══██║ ██║      ██╔══██╗  ╚██╔╝  ██╔═══╝ ██╔══██║╚════██║╚════██║",
        r"  ██████╔╝ ╚██████╔╝██║  ██║ ███████╗ ██████╔╝   ██║   ██║     ██║  ██║███████║███████║",
        r"  ╚═════╝   ╚═════╝ ╚═╝  ╚═╝ ╚══════╝ ╚═════╝    ╚═╝   ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝"
    ]
    colors = [C_PINK, C_BPINK, C_PURPLE, C_BLUE, C_CYAN, C_GREEN]
    print()
    for i, line in enumerate(banner):
        print(f"{C_BOLD}{colors[i]}{line}{C_RESET}")
    print(f"\n  {BG_PURPLE} ⚡ AUTO BYPASS SUITE ⚡ {C_RESET}  {C_BOLD}{C_CYAN}UNIVERSAL SHORTLINK BYPASS ENGINE{C_RESET}")
    print(f"  {C_DIM}{C_GRAY}✦ GTraffic / Direct GTraffic  ✦ BBMKTS  ✦ LayMa.net  ✦ TrafficVN  ✦ Link4M{C_RESET}\n")


from config import get_clipboard, copy_to_clipboard, save_destination, read_destination

get_clipboard_url = get_clipboard
save_destination_url = save_destination
read_captured_destination = read_destination



def classify_url(url: str) -> str:
    """Classifies the target URL through the unified provider registry."""
    import runner_registry
    return runner_registry.classify(url)


def show_result_card(final_url: str, duration_sec: int, engine_name: str):
    """Displays a clean synthwave result card."""
    print(f"\n  {C_CYAN}╔══════════════════════════════════════════════════════════════════════════════╗{C_RESET}")
    print(f"  {C_CYAN}║{C_RESET}  {BG_GREEN} 🏆 BYPASS THÀNH CÔNG RỰC RỠ! {C_RESET}  {C_YELLOW}[{engine_name}]{C_RESET}  {C_DIM}{C_GRAY}Thời gian: {duration_sec}s{C_RESET}               {C_CYAN}║{C_RESET}")
    print(f"  {C_CYAN}╠══════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    print(f"  {C_CYAN}║{C_RESET}  {C_BOLD}{C_WHITE}Link đích:{C_RESET} {C_BOLD}{C_CYAN}{final_url}{C_RESET}")
    print(f"  {C_CYAN}╚══════════════════════════════════════════════════════════════════════════════╝{C_RESET}\n")

    try:
        from brain import get_brain
        b_rep = get_brain().get_summary_report()
        for l in b_rep.splitlines():
            print(f"  {C_PURPLE}{l}{C_RESET}")
        print()
    except Exception:
        pass


def execute_bypass(target_url: str, headless: bool = True, quiet: bool = False,
                   output_json: bool = False, engine: str = None) -> str:
    """Executes the bypass through the unified registry, guided by BotBrain."""
    target_url = target_url.strip()

    # 🧠 BRAIN FLOW DIRECTOR: determine engine with intelligent priority
    from src.core.brain import get_brain
    brain = get_brain()
    category = brain.flow_director.determine_best_engine(target_url)

    # 🧠 BRAIN DATA CONTROLLER: start telemetry & data lifecycle session
    s_id = brain.data_controller.start_session(target_url, category)

    # Clean up old destination files
    for p in [DEST_FILE, FINAL_DEST_FILE]:
        if os.path.exists(p):
            try: os.remove(p)
            except Exception: pass

    start_time = time.time()
    import runner_registry
    res = runner_registry.execute(target_url, engine=engine, headless=headless)
    duration = int((time.time() - start_time) * 1000)
    provider = res.provider or category

    if res.success and res.destination_url:
        final_dest = res.destination_url.strip()
        brain.data_controller.finish_session(success=True, destination_url=final_dest)
        save_destination_url(final_dest)
        if output_json:
            import json
            print(json.dumps({"status": "success", "destination_url": final_dest,
                              "duration_ms": duration, "engine": provider}))
        elif quiet:
            print(final_dest)
        else:
            print(f"FINAL DESTINATION URL: {final_dest}", flush=True)
            show_result_card(final_dest, int(duration / 1000), provider)
        return final_dest

    brain.data_controller.finish_session(success=False)
    if output_json:
        import json
        print(json.dumps({"status": "error",
                          "error_code": res.error_code or "ERR_DESTINATION_NOT_FOUND",
                          "error": res.error_message or "",
                          "engine": provider}))
    elif not quiet:
        print(f"\n  {C_YELLOW}⚠ {res.error_code or 'ERR_DESTINATION_NOT_FOUND'}: "
              f"{res.error_message or 'chưa trích xuất được link đích.'}{C_RESET}\n")
    return ""


def run_loop_watcher(headless: bool = True):
    """Continuous Clipboard Watcher Mode: auto-bypasses whenever a shortlink is copied."""
    print(f"  {BG_GREEN} 🔄 CHẾ ĐỘ GIÁM SÁT CLIPBOARD TỰ ĐỘNG (LOOP WATCHER) 🔄 {C_RESET}")
    print(f"  {C_GRAY}Đang lắng nghe Clipboard... Hãy copy bất kỳ link shortlink nào (Ctrl+C).{C_RESET}")
    print(f"  {C_DIM}Nhấn Ctrl+C trong terminal để dừng lại.{C_RESET}\n")

    last_url = ""
    while True:
        try:
            curr_url = get_clipboard_url()
            if curr_url and curr_url != last_url:
                cat = classify_url(curr_url)
                if cat != "TRAFFICVN":
                    print(f"\n  {BG_BLUE} 📥 PHÁT HIỆN LINK MỚI: {C_RESET} {C_BOLD}{C_CYAN}{curr_url}{C_RESET}")
                    last_url = curr_url
                    res = execute_bypass(curr_url, headless=headless)
                    if res:
                        last_url = res  # prevent re-triggering on own destination URL
            time.sleep(0.3)
        except KeyboardInterrupt:
            print(f"\n  {C_GREEN}👋 Đã dừng chế độ giám sát.{C_RESET}\n")
            break
        except Exception:
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(
        description="⚡ Link4M Bypass Suite - Universal Auto Bypass Engine ⚡",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("url", nargs="?", default=None, help="Target shortlink URL to bypass")
    parser.add_argument("--head", "-w", "--window", action="store_true", help="Run with visible browser window")
    parser.add_argument("--headless", "-hl", action="store_true", default=True, help="Run in headless browser mode (default)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Print ONLY destination URL to stdout for piping")
    parser.add_argument("--json", action="store_true", help="Output result as JSON object")
    parser.add_argument("--engine", "-e", default=None, help="Force engine key (LINK4M, BBMKTS, GTRAFFIC, LAYMA, TRAFFICVN, OCTOLINK)")
    parser.add_argument("--loop", "-l", action="store_true", help="Continuously monitor clipboard for new shortlinks")
    parser.add_argument("--no-proxy", action="store_true", help="Disable proxy usage (direct connection)")
    parser.add_argument("--train", "--train-brain", action="store_true", help="Run autonomous training on BotBrain knowledge base")
    parser.add_argument("--brain", action="store_true", help="View current BotBrain evolution report")

    args = parser.parse_args()

    # Default to 100% headless unless explicitly requested windowed
    headless = False if args.head else True

    if args.no_proxy:
        os.environ["NO_PROXY"] = "1"

    if not args.quiet and not args.json:
        print_banner()

    if args.brain:
        from src.core.brain import get_brain
        print(get_brain().get_summary_report())
        return

    if args.train:
        from src.core.trainer import train_now
        train_now()
        return

    # Loop Mode
    if args.loop:
        run_loop_watcher(headless=headless)
        return

    target_url = args.url

    # Prompt user directly for link if not provided via CLI argument
    if not target_url:
        default_demo = "https://gtraffic.io/X3BR2OQ"
        if args.quiet or args.json:
            target_url = default_demo
        else:
            ans = input(f"  {C_BOLD}{C_CYAN}➤ Nhập link cần vượt {C_DIM}(Enter để dùng demo {default_demo}){C_RESET}: ").strip()
            target_url = ans if ans.startswith("http") else default_demo

    execute_bypass(target_url, headless=headless, quiet=args.quiet, output_json=args.json,
                   engine=args.engine)


if __name__ == "__main__":
    main()
