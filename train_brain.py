#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧠 BOT BRAIN TRAINING & INTELLIGENCE CALIBRATION CLI 🧠
Usage:
    python train_brain.py                   # Run autonomous training on all seeds
    python train_brain.py --status          # View current BotBrain report & stats
    python train_brain.py --add domain.com  # Manually register and calibrate a domain
"""

import sys
import os
import argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.brain import get_brain
from src.core.trainer import BrainTrainer

def main():
    parser = argparse.ArgumentParser(description="BotBrain Autonomous Trainer CLI")
    parser.add_argument("--status", action="store_true", help="Display BotBrain evolution report and stats")
    parser.add_argument("--add", type=str, help="Add and calibrate a specific sponsor domain")
    parser.add_argument("--seeds", nargs="+", help="Train on custom domain seeds")
    args = parser.parse_args()

    brain = get_brain()
    trainer = BrainTrainer()

    if args.status:
        print("\n" + brain.get_summary_report())
        intel = brain.memory.get("domain_intelligence", {})
        print(f"\n📊 [TRAINED DOMAINS: {len(intel)}]")
        for d, prof in sorted(intel.items(), key=lambda x: x[1].get("success_count", 0), reverse=True):
            sc = prof.get("success_count", 0)
            fc = prof.get("fail_count", 0)
            k = prof.get("traffic_key", "None")
            ip = prof.get("ip", "None")
            bt = prof.get("best_time_sec", "--")
            print(f"  • {d:<30} | Success: {sc:<3} | Fail: {fc:<3} | Key: {str(k):<10} | IP: {str(ip):<16} | Best: {bt}s")
        return

    if args.add:
        print(f"\n🎯 [CALIBRATING SPECIFIC DOMAIN]: {args.add}")
        res = trainer.train_seeds(custom_domains=[args.add])
        print(brain.get_summary_report())
        return

    custom = args.seeds if args.seeds else None
    res = trainer.train_seeds(custom_domains=custom)
    print("\n" + brain.get_summary_report())

if __name__ == "__main__":
    main()
