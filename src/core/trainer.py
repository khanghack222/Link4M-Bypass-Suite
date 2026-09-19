#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ BOT BRAIN AUTONOMOUS TRAINING & CALIBRATION ENGINE ⚡
Performs deep-learning-like calibration and heuristic intelligence training for BotBrain:
- Resolves DNS records via Google DNS API to build self-healing IP resolver mappings.
- Probes live widget endpoints (what-on, website-analytics, layma, traffic.com.vn) to extract traffic keys.
- Maps campaign aliases to verified sponsor sites.
- Auto-prunes dead domains and blacklists fraudulent redirects.
- Generates dynamic Chromium --host-resolver-rules for 100% zero DNS failure bypasses.
"""

import os
import sys
import json
import time
import re
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Tuple

from src.core.brain import get_brain, BRAIN_FILE

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# Verified Master Seed Domains across Link4M, LayMa, GTraffic, TrafficVN, BBMKTS
SEED_DOMAINS = [
    # Top Link4M / What-On / Analytics verified sponsors
    "theyhouse.co",
    "dichvuchuyennhahanoi.com",
    "ghk.gb.net",
    "rik88.gb.net",
    "dawnseeker.za.com",
    "betflik24win.co",
    "happy.jpn.com",
    "memberqq.me",
    "agobet.cc",
    "recsport.tv",
    "d55slot.vip",
    "preciouscollection.co.in",
    "ro88.cn.com",
    "aviator-slot.games",
    "santuy88slot.net",
    "hitclube.cc",
    "vitalticks.in",
    "marcjestin.me",
    "tamjaibet.cc",
    "ex8898.com",
    "ayoslots.co",
    "agilafc.com",
    "vijaylaxmigranito.in",
    "nhandinhkeobongdaonl.com",
    "soccervirtualcup.com",
    "soikeous.org",
    "tructiepkeobongda.com"
]

class BrainTrainer:
    def __init__(self):
        self.brain = get_brain()

    def resolve_domain_dns(self, domain: str) -> Tuple[Optional[str], int]:
        """Resolves IPv4 address using Google DNS JSON API."""
        try:
            url = f"https://dns.google/resolve?name={domain}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, context=_SSL_CTX, timeout=2.5) as r:
                data = json.loads(r.read())
                status = data.get('Status', -1)
                for ans in data.get('Answer', []):
                    if ans.get('type') == 1:
                        return (ans['data'], status)
                return (None, status)
        except Exception:
            return (None, -1)

    def probe_widget_script(self, domain: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Probes domain over HTTPS and HTTP to detect traffic widget key and network type."""
        for proto in [f"https://{domain}", f"http://{domain}"]:
            try:
                req = urllib.request.Request(
                    proto,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0'}
                )
                with urllib.request.urlopen(req, context=_SSL_CTX, timeout=3.0) as resp:
                    html = resp.read(65536).decode('utf-8', errors='ignore')
                    
                    network = None
                    if "what-on.com" in html:
                        network = "what-on.com"
                    elif "website-analytics.net" in html:
                        network = "website-analytics.net"
                    elif "traffic.com.vn" in html or "process-site" in html:
                        network = "traffic.com.vn"
                    elif "layma.net" in html or "api/admin/campain" in html:
                        network = "layma.net"

                    m_key = re.search(r'(?:what-on\.com|website-analytics\.net|traffic)[^"\']*?key=([a-zA-Z0-9]+)', html)
                    if m_key:
                        return (True, m_key.group(1), network or "what-on.com")
                    
                    if network or any(w in html.lower() for w in ['lấy mã', 'lay ma', 'vui lòng chờ']):
                        return (True, None, network or "generic")
            except Exception:
                pass
        return (False, None, None)

    def train_seeds(self, custom_domains: Optional[List[str]] = None) -> Dict[str, Any]:
        """Runs multi-threaded validation and training on all seed domains."""
        targets = list(dict.fromkeys((custom_domains or []) + SEED_DOMAINS))
        print(f"\n🧠 [TRAINER] Bắt đầu huấn luyện BotBrain trên {len(targets)} tên miền mục tiêu...", flush=True)
        
        results = {}
        dead_domains = []
        trained_count = 0

        def _train_single(d):
            dom = self.brain._normalize_domain(d)
            if not dom or self.brain.is_blacklisted(dom):
                return None

            ip, dns_status = self.resolve_domain_dns(dom)
            if dns_status != 0 or not ip:
                return (dom, False, None, None, None, "DNS_NXDOMAIN")

            has_sc, key, net = self.probe_widget_script(dom)
            return (dom, True, ip, key, net, "OK")

        with ThreadPoolExecutor(max_workers=8) as ex:
            batch_results = list(ex.map(_train_single, targets))

        intel = self.brain.memory.setdefault("domain_intelligence", {})
        dns_cache = self.brain.memory.setdefault("dns_cache", {})

        for item in batch_results:
            if not item:
                continue
            dom, is_live, ip, key, net, reason = item
            if not is_live:
                dead_domains.append(dom)
                # If continuous dead, add to blacklist
                self.brain.learn_failure(dom, reason=reason)
                print(f"  [-] [DEAD/NXDOMAIN] {dom:<32} (Lý do: {reason})", flush=True)
            else:
                trained_count += 1
                dns_cache[dom] = ip
                prof = intel.setdefault(dom, {
                    "domain": dom,
                    "traffic_key": key,
                    "network": net,
                    "success_count": 1,
                    "fail_count": 0,
                    "ip": ip,
                    "default_steps": 2 if net in ["what-on.com", "website-analytics.net"] else 1,
                    "winning_strategies": {"dom": 1},
                    "last_success": int(time.time())
                })
                prof["ip"] = ip
                if key:
                    prof["traffic_key"] = key
                if net:
                    prof["network"] = net
                if prof.get("success_count", 0) == 0:
                    prof["success_count"] = 1
                
                print(f"  [+] [TRAINED] {dom:<30} | IP: {ip:<15} | Key: {str(key):<10} | Net: {net}", flush=True)

        # Ingest campaign database if available
        camps_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "camps_database.json")
        camps_mapped = 0
        if os.path.exists(camps_file):
            try:
                with open(camps_file, "r", encoding="utf-8") as f:
                    camps = json.load(f)
                    for alias, target_dom in camps.items():
                        norm_t = self.brain._normalize_domain(target_dom)
                        if norm_t in intel:
                            self.brain.record_campaign(alias, f"https://{norm_t}", intel[norm_t].get("traffic_key"))
                            camps_mapped += 1
            except Exception as e_camps:
                print(f"[!] Warning reading camps_database: {e_camps}")

        self.brain.memory["stats"]["total_heals"] += len(dead_domains)
        self.brain.save()

        summary = {
            "total_tested": len(targets),
            "trained_live": trained_count,
            "pruned_dead": len(dead_domains),
            "camps_mapped": camps_mapped
        }
        print(f"\n🎉 [TRAINING COMPLETE] Đã huấn luyện {trained_count} domain live, ánh xạ {camps_mapped} campaign alias, thanh lọc {len(dead_domains)} domain chết.", flush=True)
        return summary

    def get_host_resolver_rules(self) -> str:
        """Builds an optimized Chromium host-resolver-rules string from cached DNS intelligence."""
        rules = []
        dns_cache = self.brain.memory.get("dns_cache", {})
        for dom, ip in dns_cache.items():
            if dom and ip:
                rules.append(f"MAP {dom} {ip}")
                if not dom.startswith("*."):
                    rules.append(f"MAP *.{dom} {ip}")
        # Always include static fallbacks for ad networks
        rules.extend([
            "MAP what-on.com 172.67.178.139",
            "MAP s1.what-on.com 104.21.43.112",
            "MAP website-analytics.net 104.21.52.154"
        ])
        return ", ".join(list(dict.fromkeys(rules)))

def train_now() -> Dict[str, Any]:
    trainer = BrainTrainer()
    return trainer.train_seeds()

if __name__ == "__main__":
    train_now()
