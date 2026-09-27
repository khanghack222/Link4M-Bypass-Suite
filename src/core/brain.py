import os
import sys
import json
import time
import re
from typing import Dict, Any, List, Optional, Tuple, Callable
from urllib.parse import urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BRAIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
BRAIN_FILE = os.path.join(BRAIN_DIR, "bot_brain.json")

# =====================================================================
# 1. DATA CONTROLLER (Điều hành Dữ liệu & Trạng thái Tập trung)
# =====================================================================
class DataController:
    """
    Quản lý toàn bộ vòng đời dữ liệu, phiên làm việc (Session), 
    và các tham số thích ứng (Adaptive Parameters) giữa các engine.
    """
    def __init__(self, brain_ref):
        self.brain = brain_ref
        self.active_session: Dict[str, Any] = {
            "session_id": None,
            "target_url": None,
            "platform": None,
            "stage_timings": {},
            "active_sponsor": None,
            "traffic_key": None,
            "code": None,
            "destination_url": None,
            "errors": [],
            "heals_applied": []
        }

    def start_session(self, target_url: str, platform: str) -> str:
        s_id = f"sess_{int(time.time() * 1000)}"
        self.active_session = {
            "session_id": s_id,
            "target_url": target_url,
            "platform": platform,
            "start_time": time.time(),
            "stage_timings": {"start": time.time()},
            "active_sponsor": None,
            "traffic_key": None,
            "code": None,
            "destination_url": None,
            "errors": [],
            "heals_applied": []
        }
        return s_id

    def mark_stage(self, stage_name: str, extra_data: Optional[Dict[str, Any]] = None):
        now = time.time()
        st = self.active_session.setdefault("stage_timings", {})
        prev_time = list(st.values())[-1] if st else now
        elapsed = round(now - prev_time, 2)
        st[stage_name] = now
        if extra_data:
            self.active_session.update(extra_data)

    def record_error(self, stage: str, error_msg: str):
        err_entry = {
            "stage": stage,
            "error": str(error_msg),
            "timestamp": int(time.time())
        }
        self.active_session.setdefault("errors", []).append(err_entry)

    def record_heal(self, heal_action: str):
        self.active_session.setdefault("heals_applied", []).append(heal_action)
        self.brain.register_heal(heal_action)

    def get_adaptive_timeout(self, domain: str, default_sec: int = 60) -> int:
        prof = self.brain.get_domain_profile(domain)
        if prof and prof.get("best_time_sec"):
            # Provide safe margin over historical best time
            return max(int(prof["best_time_sec"] * 1.3), 30)
        return default_sec

    def finish_session(self, success: bool, destination_url: Optional[str] = None):
        total_time = round(time.time() - self.active_session.get("start_time", time.time()), 2)
        self.active_session["total_duration"] = total_time
        self.active_session["success"] = success
        if destination_url:
            self.active_session["destination_url"] = destination_url

        # Persist session telemetry
        history = self.brain.memory.setdefault("session_history", [])
        history.append({
            "session_id": self.active_session.get("session_id"),
            "platform": self.active_session.get("platform"),
            "sponsor": self.active_session.get("active_sponsor"),
            "success": success,
            "duration": total_time,
            "heals": len(self.active_session.get("heals_applied", [])),
            "timestamp": int(time.time())
        })
        # Keep last 100 sessions
        if len(history) > 100:
            self.brain.memory["session_history"] = history[-100:]
        self.brain.save()


# =====================================================================
# 2. FLOW DIRECTOR (Điều hành Luồng & Máy trạng thái Tự phục hồi)
# =====================================================================
class FlowDirector:
    """
    Điều hành luồng thực thi thông minh (Flow Orchestrator):
    - Định tuyến runner theo độ tin cậy và lịch sử thắng (Routing Matrix).
    - Quản lý các chặng (Stages): INSPECT -> PREPARE -> RUN -> VERIFY -> RECOVER.
    - Kích hoạt ma trận dự phòng (Fallback Matrix) khi một bước gặp sự cố.
    """
    def __init__(self, brain_ref, data_ctrl: DataController):
        self.brain = brain_ref
        self.data = data_ctrl

    def determine_best_engine(self, url: str) -> str:
        """Phân loại và điều hướng runner với trọng số học từ lịch sử."""
        u = url.lower()
        if any(k in u for k in ["link999.app", "link999", "uptolink", "octolink", "linkhuongdan"]):
            return "LINK999"
        if any(k in u for k in ["gtraffic.io", "direct.gtraffic.io", "dr-client"]):
            return "GTRAFFIC"
        if any(k in u for k in ["bbmkts.com", "bbmkts", "yeumoney.com", "yeumoney"]):
            return "BBMKTS"
        if any(k in u for k in ["layma.net", "layma"]):
            return "LAYMA"
        if any(k in u for k in ["trafficvn.net", "trafficvn.com", "trafficvn"]):
            return "TRAFFICVN"
        if any(k in u for k in ["link4m.", "link4m", "link4"]):
            return "LINK4M"
        return "LINK4M"

    def plan_sponsor_strategy(self, candidates: List[str]) -> List[Tuple[str, str, int]]:
        """
        Lập chiến lược thực thi cho các ứng viên:
        Trả về danh sách tuple: (domain, best_strategy ['api'|'dom'], expected_steps)
        Ưu tiên các domain có tỉ lệ thành công cao nhất trong quá khứ.
        """
        ranked = self.brain.prioritize_candidates(candidates)
        plan = []
        for d in ranked:
            prof = self.brain.get_domain_profile(d) or {}
            strats = prof.get("winning_strategies", {})
            best_strat = max(strats, key=strats.get) if strats else "dom"
            steps = prof.get("default_steps", 2)
            plan.append((d, best_strat, steps))
        return plan

    def should_fast_track_api(self, domain: str) -> bool:
        """Kiểm tra xem domain có đủ độ tin cậy để đi luồng API siêu tốc bỏ qua UI không."""
        prof = self.brain.get_domain_profile(domain)
        if not prof:
            return False
        strats = prof.get("winning_strategies", {})
        return strats.get("api", 0) > 2 and prof.get("fail_count", 0) == 0

    def handle_stage_failure(self, stage: str, context_data: Dict[str, Any]) -> str:
        """
        Bộ não tự chữa lành khi một stage bị fail (Heuristic Recovery):
        - DNS_FAIL -> Kích hoạt Google DNS Host Resolver Rules.
        - DOM_CODE_FAIL -> Thử fetch trực tiếp qua What-On API Endpoint.
        - CAPTCHA_AUDIO_FAIL -> Chuyển đổi model transcription và retry.
        - CAMPAIGN_DEAD -> Chuyển sang candidate tiếp theo ngay lập tức.
        """
        self.data.record_error(stage, context_data.get("error", "unknown"))

        if stage == "dns_resolution":
            dom = context_data.get("domain")
            heal_msg = f"DNS fallback activated for {dom}: Auto-querying Google DNS"
            self.data.record_heal(heal_msg)
            return "SWITCH_HOST_RESOLVER"

        elif stage == "step_timeout":
            dom = context_data.get("domain")
            heal_msg = f"Step timeout on {dom}: Switching to candidate fallback"
            self.data.record_heal(heal_msg)
            return "NEXT_CANDIDATE"

        elif stage == "code_harvest":
            heal_msg = "DOM extraction empty: Forcing direct API fallback"
            self.data.record_heal(heal_msg)
            return "FORCE_API_PROBE"

        return "RETRY"


# =====================================================================
# 3. CORE BOT BRAIN SINGLETON ENGINE
# =====================================================================
class BotBrain:
    """
    Self-Learning & Self-Healing Engine for Universal Shortlink & Sponsor Bypass.
    Integrates DataController (Data Direction) and FlowDirector (Flow Direction).
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(BotBrain, cls).__new__(cls)
            cls._instance._init_brain()
        return cls._instance

    def _init_brain(self):
        os.makedirs(BRAIN_DIR, exist_ok=True)
        self.memory: Dict[str, Any] = {
            "version": "2.5.0-autonomous-director",
            "stats": {
                "total_runs": 0,
                "total_success": 0,
                "total_heals": 0,
                "time_saved_sec": 0.0,
                "last_updated": 0
            },
            "domain_intelligence": {},
            "dns_cache": {},
            "campaign_cache": {},
            "session_history": [],
            "blacklist": [
                "zbet.com", "shbet.com", "keonhacai", "catfish", "martech",
                "bong88", "fb88", "w88", "fun88", "188bet", "kubet", "thabet",
                "jun88", "789bet", "hi88", "new88", "f8bet", "soikeous.org"
            ],
            "ad_network_rules": {
                "what-on.com": {
                    "api_endpoint": "https://s1.what-on.com/widget/get_quest_code.html",
                    "code_selector": ".whatoncode, .whatoncode-wrapper",
                    "default_steps": 2
                },
                "website-analytics.net": {
                    "api_endpoint": "https://website-analytics.net/widget/get_quest_code.html",
                    "code_selector": ".whatoncode, .whatoncode-wrapper",
                    "default_steps": 2
                },
                "traffic.com.vn": {
                    "api_endpoint": "process-site",
                    "code_selector": "[id^='traffic'], .completed",
                    "default_steps": 1
                }
            }
        }
        self.load()
        # Initialize Sub-Controllers
        self.data_controller = DataController(self)
        self.flow_director = FlowDirector(self, self.data_controller)

    def load(self):
        if os.path.exists(BRAIN_FILE):
            try:
                with open(BRAIN_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        for k, v in saved.items():
                            if isinstance(v, dict) and k in self.memory and isinstance(self.memory[k], dict):
                                self.memory[k].update(v)
                            else:
                                self.memory[k] = v
            except Exception as e:
                print(f"[!] Brain load warning: {e}")

    def save(self):
        try:
            self.memory["stats"]["last_updated"] = int(time.time())
            with open(BRAIN_FILE, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Brain save error: {e}")

    def _normalize_domain(self, url_or_domain: str) -> str:
        if not url_or_domain:
            return ""
        d = url_or_domain.lower().strip()
        if "://" in d:
            d = urlparse(d).netloc
        d = re.sub(r'^www\.', '', d)
        return d.split(':')[0]

    def is_blacklisted(self, url_or_domain: str) -> bool:
        dom = self._normalize_domain(url_or_domain)
        if not dom:
            return True
        for b in self.memory.get("blacklist", []):
            if b in dom:
                return True
        return False

    def add_to_blacklist(self, domain: str, reason: str = "ad_or_malformed"):
        dom = self._normalize_domain(domain)
        if dom and dom not in self.memory["blacklist"]:
            self.memory["blacklist"].append(dom)
            self.memory["stats"]["total_heals"] += 1
            print(f"🧠 [BRAIN HEAL] Auto-blacklisted scam/ad domain: {dom} (Reason: {reason})", flush=True)
            self.save()

    def get_domain_profile(self, url_or_domain: str) -> Optional[Dict[str, Any]]:
        dom = self._normalize_domain(url_or_domain)
        return self.memory.get("domain_intelligence", {}).get(dom)

    def prioritize_candidates(self, candidate_urls_or_domains: List[str]) -> List[str]:
        valid = []
        for item in candidate_urls_or_domains:
            if not self.is_blacklisted(item):
                valid.append(item)

        def score(item):
            dom = self._normalize_domain(item)
            prof = self.memory.get("domain_intelligence", {}).get(dom, {})
            successes = prof.get("success_count", 0)
            failures = prof.get("fail_count", 0)
            has_sc = 1 if prof.get("traffic_key") else 0
            return (successes * 20) + (has_sc * 15) - (failures * 10)

        valid.sort(key=score, reverse=True)
        return valid

    def record_campaign(self, alias: str, target_sponsor_url: str, traffic_key: Optional[str] = None):
        if not alias or not target_sponsor_url:
            return
        self.memory.setdefault("campaign_cache", {})[alias] = {
            "sponsor_url": target_sponsor_url,
            "traffic_key": traffic_key,
            "timestamp": int(time.time())
        }
        self.save()

    def get_cached_campaign(self, alias: str) -> Optional[Dict[str, Any]]:
        if not alias:
            return None
        cached = self.memory.get("campaign_cache", {}).get(alias)
        if cached:
            if time.time() - cached.get("timestamp", 0) < 43200:
                return cached
        return None

    def learn_success(self, domain: str, traffic_key: Optional[str], code: str, elapsed_sec: float, winning_strategy: str = "api"):
        dom = self._normalize_domain(domain)
        if not dom:
            return

        intel = self.memory.setdefault("domain_intelligence", {})
        prof = intel.setdefault(dom, {
            "domain": dom,
            "traffic_key": traffic_key,
            "success_count": 0,
            "fail_count": 0,
            "winning_strategies": {},
            "best_time_sec": elapsed_sec,
            "last_code": code,
            "last_success": int(time.time())
        })

        prof["success_count"] += 1
        if traffic_key:
            prof["traffic_key"] = traffic_key
        prof["last_code"] = code
        prof["last_success"] = int(time.time())
        if elapsed_sec < prof.get("best_time_sec", 999.0):
            prof["best_time_sec"] = round(elapsed_sec, 2)

        strat_counts = prof.setdefault("winning_strategies", {})
        strat_counts[winning_strategy] = strat_counts.get(winning_strategy, 0) + 1

        self.memory["stats"]["total_success"] += 1
        self.memory["stats"]["total_runs"] += 1
        self.memory["stats"]["time_saved_sec"] += max(0.0, 30.0 - elapsed_sec)

        print(f"🧠 [BRAIN LEARN] Memorized success pattern for '{dom}' | Strategy: {winning_strategy} | Code: {code} | Best Time: {prof['best_time_sec']}s", flush=True)
        self.save()

    def learn_failure(self, domain: str, reason: str):
        dom = self._normalize_domain(domain)
        if not dom:
            return
        intel = self.memory.setdefault("domain_intelligence", {})
        prof = intel.setdefault(dom, {
            "domain": dom,
            "traffic_key": None,
            "success_count": 0,
            "fail_count": 0,
            "last_fail_reason": reason,
            "last_fail": int(time.time())
        })
        prof["fail_count"] += 1
        prof["last_fail_reason"] = reason
        prof["last_fail"] = int(time.time())

        if prof["fail_count"] >= 3 and prof["success_count"] == 0:
            self.add_to_blacklist(dom, reason=f"continuous_failures: {reason}")

        self.memory["stats"]["total_runs"] += 1
        self.save()

    def register_heal(self, heal_description: str):
        self.memory["stats"]["total_heals"] += 1
        print(f"⚡ [BRAIN SELF-HEAL] {heal_description}", flush=True)
        self.save()

    def get_host_resolver_rules(self) -> str:
        """Returns dynamic Chromium host-resolver-rules from cached intelligence."""
        rules = []
        dns_cache = self.memory.get("dns_cache", {})
        for dom, ip in dns_cache.items():
            if dom and ip:
                rules.append(f"MAP {dom} {ip}")
                if not dom.startswith("*."):
                    rules.append(f"MAP *.{dom} {ip}")
        # Universal ad-network fallbacks
        rules.extend([
            "MAP ghk.gb.net 172.67.214.159",
            "MAP rik88.gb.net 104.21.60.53",
            "MAP *.gb.net 172.67.214.159",
            "MAP what-on.com 172.67.178.139",
            "MAP s1.what-on.com 104.21.43.112",
            "MAP website-analytics.net 104.21.52.154"
        ])
        return ", ".join(list(dict.fromkeys(rules)))

    def train(self, custom_domains: Optional[List[str]] = None) -> Dict[str, Any]:
        """Runs the autonomous trainer to learn and verify domains."""
        from src.core.trainer import BrainTrainer
        trainer = BrainTrainer()
        return trainer.train_seeds(custom_domains=custom_domains)

    def get_summary_report(self) -> str:
        st = self.memory.get("stats", {})
        total = st.get("total_runs", 0)
        succ = st.get("total_success", 0)
        rate = (succ / total * 100) if total > 0 else 0.0
        known_domains = len(self.memory.get("domain_intelligence", {}))
        heals = st.get("total_heals", 0)
        recent_sessions = len(self.memory.get("session_history", []))

        lines = [
            "🧠 --- BOT BRAIN AUTONOMOUS DIRECTOR REPORT ---",
            f"• Knowledge Base: {known_domains} verified sponsor domains cached",
            f"• Active Sessions Logged: {recent_sessions} pipeline executions",
            f"• Total Missions Run: {total} | Successes: {succ} ({rate:.1f}%)",
            f"• Self-Healing Adaptations: {heals} events dynamically applied",
            f"• Estimated Automation Time Saved: {st.get('time_saved_sec', 0.0):.1f}s",
            "• Flow Director: Multi-stage State Machine & Adaptive Timeouts Active",
            "--------------------------------------------------"
        ]
        return "\n".join(lines)

_BRAIN_SINGLETON = None

def get_brain() -> BotBrain:
    global _BRAIN_SINGLETON
    if _BRAIN_SINGLETON is None:
        _BRAIN_SINGLETON = BotBrain()
    return _BRAIN_SINGLETON
