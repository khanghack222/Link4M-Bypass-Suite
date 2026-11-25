# Implementation Plan

## [Overview]

Build a single unified provider registry/dispatch layer so all four front-ends of Link4M Bypass Suite (`src/ui/menu.js`, `src/cli.py`, `service/` FastAPI + worker, `bot_discord.js`) route every supported shortlink through one code path instead of four hand-maintained dispatch tables.

Today the suite has **seven working engines** but **six independent dispatch implementations**, each with its own classifier, its own provider naming, and its own fast-path decode copy:

| Face | File | Current dispatch | Providers covered |
|---|---|---|---|
| Interactive menu | `src/ui/menu.js` | `isXxxUrl()` ×6 + `runBypassXxx()` ×6 (~560 duplicated lines) + `dispatchUrl()` | Link4M, BBMKTS, Gtraffic, LayMa, OctoLink, TrafficVN |
| Universal CLI | `auto_bypass.py` | `classify_url()` + `execute_bypass()` if/elif chain + inline zero-click decoders | Link999/Octo, Gtraffic, BBMKTS, LayMa, TrafficVN, Link4M |
| Brain router | `src/core/brain.py` | `FlowDirector.determine_best_engine()` — a **third** classifier with different strings and a silent `LINK4M` default | same 6 (returns `LINK999`, never `GENERIC`) |
| JSON CLI | `src/cli.py` | its own base64 fast-path + `bypass.run()` directly | Link4M only |
| HTTP service | `service/providers.py` + `service/worker.py` | `PROVIDERS` dict (link4m only) + `fast_decode()`; worker **hard-rejects** any provider != `link4m` | link4m only |
| Discord bot | `bot_discord.js` | no classifier; always spawns `auto_bypass.py` | inherits auto_bypass |

A skeleton already exists and is **currently unused by every face** (only `tests/test_fast_paths_and_pool.py` imports it):

- `src/core/base_runner.py` — `BypassResult` envelope + `BaseBypassRunner` template method (`pre_flight` → `execute_flow`) with `BLOCKED_DESTINATION_PATTERNS`.
- `src/core/runner_registry.py` — `register_runner()` / `get_runner()` / `execute_engine()`.
- `src/core/runners.py` — 6 registered runner subclasses (`BBMKTS`, `GTRAFFIC`, `LINK4M`, `LAYMA`, `OCTOLINK`, `TRAFFICVN`).

This plan promotes that skeleton to the single source of truth: one provider table, one classifier, one `execute()` entry, one fast-path decoder — and rewrites the four faces to consume it. Scope is routing/contract only: **no engine internals are rewritten**, and every log string the faces currently scrape (`Target … URL:`, `FINAL DESTINATION URL:`, `>>> http…<<<`, `DESTINATION URL INTERCEPTED FROM API:`) is preserved byte-for-byte so no front-end behaviour silently changes.

Non-goals: no new engines, no captcha/solver changes, no re-architecture of `sponsor.py` / `recaptcha_solver.py`, no removal of the duplicated `scripts/*.py` copies (tracked separately), no doc rewrite.

Environment confirmed on this box: Python 3.13.5 + `.venv/` (fastapi + playwright import OK), Node v26.13.1, and the offline test scripts already pass (`.venv/bin/python tests/test_fast_paths_and_pool.py` → `ALL UPGRADE TESTS PASSED`).

## [Types]

### 1. Canonical provider keys + alias map (new, `src/core/runner_registry.py`)

Canonical keys are the registry primary key and the string every face passes. Current faces disagree (`LINK999` in `auto_bypass.py`/`brain.py` vs `OCTOLINK` in `runners.py`/`menu.js`), so the alias map is mandatory.

```python
# canonical key  ->  historical / face-local spellings that must resolve to it
PROVIDER_ALIASES: dict[str, tuple[str, ...]] = {
    "LINK4M":     ("LINK4M", "LINK4", "L4M"),
    "BBMKTS":     ("BBMKTS", "BBMKT", "YOUMONEY", "YEUMONEY"),
    "GTRAFFIC":   ("GTRAFFIC", "G-TRAFFIC", "DIRECT_GTRAFFIC"),
    "LAYMA":      ("LAYMA", "LAYMA.NET"),
    "TRAFFICVN":  ("TRAFFICVN", "TRAFFIC_VN", "IATUM"),
    "OCTOLINK":   ("OCTOLINK", "OCTO", "LINK999", "UPTOLINK",
                   "LINKHUONGDAN", "SHORTEARN"),
    "DECODE":     ("DECODE", "BASE64", "FASTPATH"),
}
GENERIC_KEY = "GENERIC"   # returned by classify() for unrecognised hosts; never executable
```

### 2. `EngineKind` enum (new)

```python
class EngineKind(str, Enum):
    BROWSER       = "browser"        # in-process Playwright/patchright engine module
    EXTERNAL_NODE = "external_node"  # Node subprocess (octolink_runner.js)
    DECODE        = "decode"         # pure string/base64 resolution, no browser, no network
```

### 3. `ProviderSpec` dataclass (new) — the whole provider table

```python
@dataclass(frozen=True)
class ProviderSpec:
    key: str                      # canonical key, e.g. "GTRAFFIC"
    aliases: tuple[str, ...]      # accepted spellings, upper-cased at lookup
    hosts: tuple[str, ...]        # apex hosts; match is `host == h or host.endswith("." + h)`
    url_pattern: re.Pattern | None  # path regex for the alias/slug, None = accept any path
    kind: EngineKind
    runner: type["BaseBypassRunner"] | None   # None for DECODE
    module: str                   # engine module/entry for logging + docs, e.g. "gtraffic_runner"
    ready: bool = True            # False = declared, no engine yet (kept for roadmap entries)
```

`url_pattern` deliberately mirrors the patterns already in `service/providers.py` and the host lists already in `auto_bypass.classify_url()`, `brain.FlowDirector.determine_best_engine()` and `menu.js` `isXxxUrl()` — the union of those three, so behaviour is a strict superset of what any face accepts today. Concretely:

| key | hosts | url_pattern | kind |
|---|---|---|---|
| LINK4M | link4m.net, .com, .co, .org, .vip, .pro, .me, .app, link4m.net | `/go/([A-Za-z0-9_-]+)` | BROWSER |
| BBMKTS | bbmkts.com, yeumoney.com | `/go/([A-Za-z0-9_-]+)` (+ `/go/file/<payload>` handled by pre_flight) | BROWSER |
| GTRAFFIC | gtraffic.io, direct.gtraffic.io, dr-client.gtraffic.io, client.gtraffic.io | `/([A-Za-z0-9_-]+)$` | BROWSER |
| LAYMA | layma.net | `/([A-Za-z0-9_-]+)$` | BROWSER |
| TRAFFICVN | trafficvn.com, trafficvn.net | `/(?:get/)?([A-Za-z0-9_-]+)` | BROWSER |
| OCTOLINK | octolink.vip, link999.app, uptolink.*, linkhuongdan.* | None (slug form varies per brand) | EXTERNAL_NODE |
| DECODE | (n/a) | None | DECODE |

### 4. `BypassResult` extension (`src/core/base_runner.py`)

Existing fields (`success`, `destination_url`, `engine`, `duration_ms`, `error_code`, `error_message`, `metadata`) stay — `tests/test_fast_paths_and_pool.py` asserts on `success`, `destination_url`, `engine`, `metadata["fast_path"]`, so they must not change. Additive only:

```python
@dataclass
class BypassResult:
    success: bool
    destination_url: Optional[str] = None
    engine: str = "UNKNOWN"          # canonical provider key
    duration_ms: float = 0.0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # --- new, additive ---
    provider: Optional[str] = None   # canonical key (== engine for engines; "DECODE" for fast paths)
    cached: bool = False             # reserved: service cache hit, always False from registry.execute
    stage: Optional[str] = None      # "pre_flight" | "browser" | "node" — for service/worker retry policy
```

`to_dict()` gains the three keys (extra keys are safe: `service/worker.py` reads `res.get("ok")`/`res.get("destination")`, which is unified in the Functions section).

### 5. `Match` compatibility (`service/providers.py`)

`service/app.py` imports `fast_decode, normalize, parse, supported` and passes `Match(provider, key, url, kind)` into `_do_bypass()`. The dataclass **stays exactly as-is**; `parse()` becomes a thin wrapper over `runner_registry.detect()` + its own key extraction, so `app.py` needs no changes.

### 6. Engine return-shape union (contract being normalised, no new type)

Engines currently return three different shapes; the registry adapter collapses them into `str | None`:

- `str | None` — `bypass.run()`, `bbmkts_runner.run()`, `gtraffic_runner.run()`, `layma_runner.run()`, `trafficvn_runner.run()`
- `dict` — `link4m_engine.bypass_alias()` → `{"ok": bool, "destination": str, "stage": str, "code": …, "sponsor": …, "server": …}`
- Node promise result — `octolink_runner.runBypass(url, opts, onLog)` → `{success: bool, finalUrl: str, reason?: str}` (consumed by `menu.js`, currently **not** emitted to stdout — `runners.py` reads `destination_url.txt` instead, which is a race; the plan fixes this by having the JS runner print one JSON line)

### 7. Error codes (existing `src/core/errors.py`, reused not extended)

`ERR_PREFLIGHT_FAIL`, `ERR_CAPTCHA_BLOCKED`, `ERR_COUNTDOWN_TIMEOUT`, `ERR_SPONSOR_NOT_FOUND`, `ERR_DESTINATION_NOT_FOUND`, `ERR_BROWSER_CRASH` already cover the paths. The registry adds no new codes but introduces two sentinel values used only in `BypassResult.error_code`:

- `ERR_PROVIDER_UNKNOWN` — `detect()` returned `None` / `GENERIC` (replaces today's silent Link4M default)
- `ERR_RUNNER_NOT_FOUND` — key resolved but `spec.runner is None` or `spec.ready is False` (already defined in `runner_registry.execute_engine`)

## [Files]

### New files

| Path | Purpose |
|---|---|
| `src/core/provider_table.py` | **New single source of truth**: `EngineKind`, `ProviderSpec`, `PROVIDER_TABLE` (the 7 specs from the Types table), `PROVIDER_ALIASES`, `GENERIC_KEY`. Deliberately data-only — imports nothing from `runners.py`, which avoids the registry↔runners import cycle (`runners.py` imports the table and self-registers via the existing `@register_runner` decorator). |
| `src/core/engine_adapters.py` | **New**: per-engine call shims + `dest_from(value)` normaliser. Each shim is the only place that knows an engine's import name, call signature and return shape (`bypass.run`, `bbmkts_runner.run`, `gtraffic_runner.run`, `layma_runner.run`, `trafficvn_runner.run`, `link4m_engine.bypass_alias`, `octolink_runner.js` subprocess). Keeps `runners.py` declarative. |
| `src/bypass_api.py` | **New**: process-level façade for the JS faces — `python -m src.bypass_api --url <u> [--engine KEY] [--headless] [--json] [--list]`. Prints the log lines the engines already print (so `formatLogLine()` keeps working), then `FINAL DESTINATION URL: <u>`, plus one JSON line when `--json`. This is the **only** command `menu.js`, `bot_discord.js` and `service/worker.py` shell out to. |
| `tests/test_provider_registry.py` | **New offline** registry contract tests, script-style with `if __name__ == "__main__"` (matches `tests/test_fast_paths_and_pool.py`). No network, no browser. |
| `tests/test_engine_adapters.py` | **New offline** adapter/normaliser tests using stubbed engine modules injected into `sys.modules` — no real browser, no real network. |

### Modified files

| Path | Specific changes |
|---|---|
| `src/core/runner_registry.py` | Becomes the registry API. Keeps `register_runner` / `get_runner` / `execute_engine` (imported by `tests/test_fast_paths_and_pool.py`; `execute_engine` keeps its signature and now delegates). Adds: path bootstrap so it imports both flat (`import runner_registry`) and packaged (`from src.core import runner_registry`); `detect(url) -> ProviderSpec \| None`; `classify(url) -> str` (canonical key or `"GENERIC"`); `normalize_key(raw) -> str \| None`; `supported() -> list[str]`; `parse_key(url) -> tuple[str, str] \| None`; `fast_decode(url) -> str \| None`; `execute(url, *, engine=None, headless=True) -> BypassResult`. `runners` is imported lazily inside `execute()` so registration is guaranteed. |
| `src/core/runners.py` | Import fix + contract fix. Keep flat imports (repo convention) but tolerate package import. Add class attrs `provider_key: str` and `standalone_browser: bool`. Every `execute_flow` delegates to `engine_adapters` instead of importing its engine directly. `Link4MRunner.execute_flow` keeps the `link4m_engine.bypass_alias` path behind `L4M_ENGINE` (`cdp` \| `legacy`) — that CDP flow is the proven service path and must stay reachable. `OctoLinkRunner.execute_flow` stops reading `destination_url.txt` (a race) and reads the JSON line from the node subprocess stdout instead. |
| `src/core/base_runner.py` | Additive `BypassResult` fields (`provider`, `cached`, `stage`) + `to_dict()` update. `BaseBypassRunner` gains `standalone_browser: bool = True`; `run()` skips `BrowserPool` entirely when True — today every engine launches its own browser, so the pooled context is acquired and thrown away (a live double-browser bug on the `test_template_run_fastpath` path). Sets `provider` and `stage` on every return. |
| `auto_bypass.py` | `classify_url()` becomes a thin wrapper over `runner_registry.classify()` and must still return `"GENERIC"` for unknown hosts (`tests/test_unit_core.py`, `tests/test_suite_integrity.py` assert on it). `execute_bypass()`'s if/elif chain is replaced by one `runner_registry.execute()` call; the two inline zero-click blocks (BBMKTS `/go/file/` base64, GTraffic API leak) are deleted and delegated to runner `pre_flight`. Keeps `--json`, `--quiet`, `--loop`, `--train`, `--brain`; adds `--engine KEY`. Keeps printing `FINAL DESTINATION URL:` / `DESTINATION URL INTERCEPTED FROM API:` (menu + bot scrape these). |
| `src/core/brain.py` | `FlowDirector.determine_best_engine()` delegates to `runner_registry.classify()` and maps `GENERIC -> "LINK4M"`, preserving brain's public contract (callers never see `GENERIC`). Removes the fourth copy of the host tables. |
| `src/cli.py` | `resolve_bypass()` calls `runner_registry.execute()`; `StderrRedirector` + pure-JSON stdout contract preserved, both existing fast paths now via `runner_registry.fast_decode()`. Adds `--engine KEY` and `--list`. The `python -m src.cli --url …` contract used by `tests/test_r3_cli_api.py` and `tests/test_tier5_cli_api.py` is unchanged. |

| `src/ui/menu.js` | Delete `runBypassLink4M` / `runBypassBBMKTS` / `runBypassGtraffic` / `runBypassLayMa` / `runBypassTrafficVN` (5 near-identical spawn+logger blocks, ~450 lines) and the 5 `isXxxUrl()` predicates. Add one `runEngine(targetUrl, engineKey, headless)` that spawns `python -m src.bypass_api --url … --json` and pipes stdout through the untouched `formatLogLine()`. `runBypassOctolink` keeps its in-process `require(OCTO_RUNNER)` path (it is the only provider giving live progress callbacks) but its result card is reused. `dispatchUrl()` consults the registry (`--list`, cached at start-up) instead of the 5 predicates. Menu numbering, labels and colours are unchanged. |
| `service/providers.py` | `PROVIDERS` dict deleted; `parse()`, `supported()`, `fast_decode()`, `normalize()` become wrappers over `runner_registry` (with the same `sys.path` bootstrap `service/worker.py` already uses). `Match` dataclass unchanged. |
| `service/worker.py` | `_run_job()` drops the `if job["provider"] != "link4m": error` rejection and calls `runner_registry.execute(url=…, engine=job["provider"], headless=True)` inside `asyncio.to_thread`, mapping `BypassResult` → the `{"ok", "destination"}` shape it already expects. `L4M_ENGINE=cdp` (default in the service) keeps `link4m_engine.bypass_alias` as the Link4M path — Chrome-CDP is the proven service flow. |
| `service/config.py`, `service/app.py`, `src/core/link4m_engine.py` | Replace the hard-coded `os.path.expanduser("~/Link4M-Bypass-Suite")` `REPO` constant with a `__file__`-relative derivation, keeping the `L4M_REPO` env override. Today the service cannot start from any other checkout path, and `link4m_engine.py` (`REPO`, `DEST_FILE`, `LOG_DIR`) has the same assumption. |
| `bot_discord.js` | Still spawns `auto_bypass.py`; add `--json` and parse the JSON line instead of re-reading `destination_url.txt` (removes a file race under its 2-way concurrency). `/platforms` list generated from `python -m src.bypass_api --list`. No command names, embeds or button IDs change. |
| `src/core/__init__.py` | Add a `_CORE_DIR` bootstrap consistent with `bypass.py` so `from src.core import runner_registry` works when invoked from the repo root. |

### Deleted / moved files

| Path | Action |
|---|---|
| `src/core/runner_registry.py` old body | Rewritten **in place**, not deleted — `tests/test_fast_paths_and_pool.py` imports `get_runner, execute_engine` from it, and those names must survive. |
| `src/ui/menu.js` functions `isLink4mUrl`, `isBbmktsUrl`, `isGtrafficUrl`, `isLaymaUrl`, `isTrafficvnUrl`, `runBypassLink4M`, `runBypassBBMKTS`, `runBypassGtraffic`, `runBypassLayMa`, `runBypassTrafficVN` | Deleted, replaced by `runEngine()` + registry lookup. `isOctolinkUrl` stays (feeds the in-process node path). |
| `auto_bypass.py` inline BBMKTS `/go/file/` base64 block and GTraffic `api/url/get` leak block | Deleted, replaced by `BBMKTSRunner.pre_flight()` / `GTrafficRunner.pre_flight()` (logic already exists there verbatim, incl. the `data_link` dict-or-str handling). |
| *(nothing else)* | No engine module, solver, sponsor module, doc or test is deleted. `scripts/final_bypass_100.py` (byte-identical duplicate of `src/core/final_bypass_100.py`), `scripts/decode_link.py` and `scripts/shortlink_factory.py` (drifted copies) are **explicitly out of scope** — flagged for a follow-up cleanup so this change stays reviewable. |

### Configuration updates

- New optional env vars, defaults preserving today's behaviour: `L4M_ENGINE` (`legacy`\|`cdp`), `L4M_REPO` (checkout root override), `BYPASS_API_JSON` (`1` → `src/bypass_api.py` always emits its JSON line).
- `package.json`: add `"bypass": "python -m src.bypass_api"` and `"list": "python -m src.bypass_api --list"` beside the existing `start` / `bot` scripts.
- No `.env` schema change; no `Dockerfile` / `docker-compose.yml` change (`Dockerfile` already sets `PYTHON_PATH`).

## [Functions]

### New functions — `src/core/provider_table.py`

- `spec_for(key: str) -> ProviderSpec | None` — alias-aware lookup (`"link999"` → `OCTOLINK` spec), case-insensitive, whitespace-trimmed.
- `canonical_key(raw: str) -> str | None` — alias → canonical key, `None` when unknown.

### New functions — `src/core/runner_registry.py`

```python
def detect(url: str) -> Optional[ProviderSpec]       # host + url_pattern match; None if unrecognised
def classify(url: str) -> str                        # canonical key, or GENERIC_KEY
def normalize_key(raw: str) -> Optional[str]         # delegate to provider_table.canonical_key
def supported() -> list[str]                         # sorted canonical keys incl. DECODE
def parse_key(url: str) -> Optional[tuple[str, str]]  # (canonical_key, slug); slug = pattern group(1) or ""
def fast_decode(url: str) -> Optional[str]            # DECODE: /go/file/<b64|pct>, query base64, hash base64
def execute(url: str, *, engine: Optional[str] = None, headless: bool = True) -> BypassResult
```

`execute()` algorithm, written out so implementation is unambiguous:

1. `url = (url or "").strip()`; empty → `BypassResult(success=False, error_code="ERR_PROVIDER_UNKNOWN", error_message="empty url")`.
2. `key = normalize_key(engine) if engine else classify(url)`.
3. `key` is `None`/`GENERIC_KEY` → return `ERR_PROVIDER_UNKNOWN`. There is **no silent Link4M fallback** inside the registry; `auto_bypass.py` and `brain.py` keep their own explicit fallback so their public behaviour is unchanged.
4. `spec = spec_for(key)`; `spec.runner is None or not spec.ready` → `ERR_RUNNER_NOT_FOUND`.
5. Fast path first: `fast = fast_decode(url)`; if truthy and accepted by the runner's destination validator → `BypassResult(success=True, engine="DECODE", provider="DECODE", metadata={"fast_path": True}, stage="pre_flight")`.
6. Otherwise `runner = spec.runner()`; `res = runner.run(url)`; stamp `res.provider = res.provider or spec.key`; `res.stage = res.stage or ("pre_flight" if res.metadata.get("fast_path") else "browser")`; return `res`.

`execute()` never raises for a bypass failure — every engine's own error path already lands in `BypassResult`. It only raises for programming errors (unknown table entry), which is deliberate: `tests/` should fail loudly on a bad table.

### New functions — `src/core/engine_adapters.py`

```python
def dest_from(value: Any) -> Optional[str]
    # str                        -> value.strip() when it starts with http, else None
    # dict                       -> first truthy of destination / finalUrl / url / link / redirect /
    #                               data_link.url / data_link (when str); None when ok is False
    # None / other               -> None

def run_bbmkts(url, headless) -> Optional[str]        # bbmkts_runner.run(url, headless=headless)
def run_gtraffic(url, headless) -> Optional[str]      # gtraffic_runner.run(url, headless=headless)
def run_layma(url, headless) -> Optional[str]         # layma_runner.run(url, headless=headless)
def run_trafficvn(url, headless) -> Optional[str]     # trafficvn_runner.run(url, headless=headless)
def run_link4m_legacy(url, headless) -> Optional[str] # bypass.run(url, headless=headless)
def run_link4m_cdp(alias, keep_open=False) -> Optional[str]
    # link4m_engine.bypass_alias(alias, keep_open=keep_open) -> dest_from(dict)
def run_octolink(url, headless, timeout=120) -> Optional[str]
    # subprocess.run([node, src/core/octolink_runner.js, url, *(["--headless"] if headless else []), "--json"],
    #                capture_output=True, text=True, timeout=timeout)
    # scan stdout lines from the last backwards, json.loads, take first with finalUrl/success
```

Every adapter imports its engine **inside the function** (lazy). `bypass.py`, `layma_runner.py`, `gtraffic_runner.py` and `trafficvn_runner.py` all read `sys.argv` and take action at import scope in their `__main__` paths, so top-level imports would have side effects on the host process (`auto_bypass.py`, `service/worker.py`).

### New functions — `src/bypass_api.py`

```python
def build_parser() -> argparse.ArgumentParser    # --url, --engine, --headless/--head, --json, --list, --timeout
def list_payload() -> dict                       # {"supported": [...], "engines": {KEY: module}, "generated_by": "4479"}
def run_once(url, engine, headless) -> BypassResult
def emit_result(res: BypassResult, as_json: bool) -> int
def main(argv: list[str] | None = None) -> int
```

`main()` behaviour contract (this is what the JS faces depend on, so it is fixed):

- `--list` → print the JSON payload, exit 0, never launch a browser or import an engine module.
- otherwise → `run_once()` (which is a thin `runner_registry.execute()` call). Engine log lines reach stdout untouched because engines print directly; the façade adds nothing that could break `formatLogLine()` matching.
- success → `log_result_card(dest, provider)` **and** one bare `FINAL DESTINATION URL: <dest>` line, exit 0.
- failure → one `[ERROR] <error_code>: <error_message>` line, exit 1.
- `--json` / `BYPASS_API_JSON=1` → additionally emit exactly one line `__BYPASS_JSON__{...}` carrying `BypassResult.to_dict()`; the `__BYPASS_JSON__` prefix keeps it separable from engine noise for `bot_discord.js`.
- `--timeout` maps onto the engine's own timeout kwarg where the adapter exposes one (`run_octolink`); for the browser engines it is accepted and recorded in `metadata["timeout"]`, since those engines own their internal deadlines.

### New functions — tests

`tests/test_provider_registry.py`:

- `test_detect_and_classify_matrix()` — union table of every host form accepted today by `auto_bypass.classify_url()`, `brain.FlowDirector.determine_best_engine()` and the five `menu.js` predicates; asserts canonical results (incl. `link999` → `OCTOLINK`, `octolink.vip` → `OCTOLINK`, `unknownlink.com` → `GENERIC`).
- `test_alias_normalization()` — `LINK999`/`uptolink`/`linkhuongdan`/`octo` → `OCTOLINK`; `yeumoney` → `BBMKTS`; `nonsense` → `None`.
- `test_parse_key_slugs()` — `/go/2kCcIqn` → `("LINK4M", "2kCcIqn")`; `/get/MFGm2tAlcSn` → `("TRAFFICVN", "MFGm2tAlcSn")`; `direct.gtraffic.io/X3BR2OQ` → `("GTRAFFIC", "X3BR2OQ")`.
- `test_execute_unknown_provider()` — asserts `ERR_PROVIDER_UNKNOWN` and that no engine module got imported (checked via `sys.modules` diff).
- `test_execute_preflight_only()` — `BBMKTS` `/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS90YXJnZXQtZmlsZQ==` resolves offline in < 50 ms with `metadata["fast_path"] is True` and `stage == "pre_flight"`.
- `test_supported_and_list_payload()` — `supported()` contains all six engine keys plus `DECODE`; `bypass_api.list_payload()` is JSON-serialisable.

`tests/test_engine_adapters.py`:

- `test_dest_from_shapes()` — `str`, `{"ok": True, "destination": …}`, `{"success": True, "finalUrl": …}`, `{"data_link": {"url": …}}`, `{"data_link": "https://…"}`, `{"ok": False}`, `None` → each maps to the documented value.
- `test_adapters_call_stub_engines()` — inject `types.ModuleType` stubs into `sys.modules` for `bbmkts_runner`, `gtraffic_runner`, `layma_runner`, `trafficvn_runner`, `bypass`, `link4m_engine`; assert each adapter passes the documented kwargs and normalises the stub's return value.
- `test_octolink_stdout_parsing()` — stub `subprocess.run` to return a fake stdout containing log lines plus a trailing `{"success": true, "finalUrl": "https://example.com/x"}`; assert the adapter returns that URL and that a non-JSON stdout returns `None` (never crashes).
- `test_destination_validator_blocks_ads()` — `is_valid_destination()` rejects every pattern in `BLOCKED_DESTINATION_PATTERNS` and accepts a plain destination.

### Modified functions

| Function | File | Required change |
|---|---|---|
| `register_runner(engine_key)` | `src/core/runner_registry.py` | Decorator unchanged, but registration now validates the key against `PROVIDER_TABLE` and prints one stderr warning on an unknown key instead of silently registering it. |
| `get_runner(engine_key)` | `src/core/runner_registry.py` | Alias-aware: `get_runner("link999")` must return `OctoLinkRunner`. Must keep returning a **class instance** — `tests/test_fast_paths_and_pool.py::test_runner_registry_lookup` asserts `isinstance(...)`. |
| `execute_engine(engine_key, target_url, headless=True)` | `src/core/runner_registry.py` | Delegate to `execute(url=target_url, engine=engine_key, headless=headless)`; keep `headless` in the signature and record it in `metadata["headless"]`. |
| `BaseBypassRunner.run(target_url, context=None, page=None)` | `src/core/base_runner.py` | Honour `standalone_browser`; skip `BrowserPool` when True and call `execute_flow(None, None, url)`; populate `provider`/`stage`; preserve `metadata["fast_path"]` semantics exactly (`True` only on the pre-flight path — asserted by the existing test). |
| `Link4MRunner.execute_flow(page, context, url)` | `src/core/runners.py` | Route through `engine_adapters.run_link4m_legacy` (default) or `run_link4m_cdp` when `L4M_ENGINE=cdp`; the CDP path receives the link4m slug from `parse_key()`, not the full URL (`bypass_alias` builds `https://link4m.net/go/{alias}` itself). |
| `OctoLinkRunner.execute_flow(page, context, url)` | `src/core/runners.py` | Use `engine_adapters.run_octolink` (stdout JSON) instead of `subprocess.run` + `destination_url.txt`; keep raising `DestinationNotFound` with the same message shape so error codes are unchanged. |
| `BBMKTSRunner.execute_flow` / `GTrafficRunner.execute_flow` / `LayMaRunner.execute_flow` / `TrafficVNRunner.execute_flow` | `src/core/runners.py` | Delegate to their adapter. LayMa and TrafficVN inherit `pre_flight = None` (no fast path exists in those engines today) — no behaviour invented. |
| `classify_url(url)` | `auto_bypass.py` | `return runner_registry.classify(url)`. Still returns `"GENERIC"`. It **no longer returns `"LINK999"`** — the alias map normalises it to `OCTOLINK`, so `tests/test_unit_core.py`'s `("https://octolink.vip/abc", "LINK999")` and `tests/test_suite_integrity.py`'s expectations are updated in the same commit, plus `run_loop_watcher`'s `cat != "TRAFFICVN"` comparison switches to the canonical key. |
| `execute_bypass(target_url, headless, quiet, output_json)` | `auto_bypass.py` | Body replaced by: brain session start → `runner_registry.execute()` → brain session finish → the existing `output_json` / `quiet` / `show_result_card` print branches (unchanged). The if/elif chain and both inline fast-path blocks are deleted. Signature and return type (`str`, `""` on failure) are unchanged, so `bot_discord.js` and `test_suite_integrity.py` keep working. |
| `run_loop_watcher(headless)` | `auto_bypass.py` | Use `runner_registry.classify()`; keep the "don't re-trigger on our own destination" guard. |
| `FlowDirector.determine_best_engine(url)` | `src/core/brain.py` | `k = runner_registry.classify(url)`; `return "LINK4M" if k in (None, "GENERIC") else k`. Public contract preserved (callers never see `GENERIC`), fourth host-table copy deleted. |
| `resolve_bypass(target_url, headless, timeout, proxy)` | `src/cli.py` | Keep both string fast paths, now via `runner_registry.fast_decode()`, then `res = runner_registry.execute(url, headless=headless)`; `raise RuntimeError(res.error_message or res.error_code)` when `not res.success`; keep the `DEST_FILE` fallback read and the `bbmkts`/`link4m` rejection filter. `--proxy` is accepted and documented as "only honoured by the Link4M engine; other engines connect directly" — one `--help` line, no silent dropping. |

| `_run_job(job_id)` | `service/worker.py` | Delete the `provider != "link4m"` gate. Run the engine via `await asyncio.to_thread(runner_registry.execute, job["url"], engine=job["provider"], headless=True)` wrapped in the existing `asyncio.wait_for(..., CFG.JOB_TIMEOUT)`; map `BypassResult` → `set_status("success", destination=…)` + `cache_put`, else `last_err = res.error_message or res.error_code`. Retry loop, `MAX_TRIES`, `RETRY_DELAY` and the `_resolve()` waiter signalling are untouched. |
| `_blocking_bypass(alias, keep_open=False)` | `service/worker.py` | Kept, but only used when `job["provider"] == "link4m"` **and** `L4M_ENGINE == "cdp"` (the service default). Any other case goes through the registry. |
| `WorkerPool.start()` | `service/worker.py` | `ensure_chrome()` may only run when at least one provider needs CDP; gate it on `L4M_ENGINE == "cdp"` so a non-Link4M-only deployment does not require Chrome on `:9222`. Log line stays the same. |
| `parse(url)` | `service/providers.py` | Wrapper: `key, slug = runner_registry.parse_key(url)`; return `Match(provider=key.lower(), key=slug, url=url, kind=spec.kind)`. `app.py` never string-compares provider names except through `_from_job`, so lowercase keys are safe and keep the existing API payload shape (`"provider": "link4m"`). |
| `supported()` | `service/providers.py` | `return sorted(k.lower() for k in runner_registry.supported() - {"DECODE"})` — the `/` and `/api/v1/supported` payloads stay a list of lowercase provider names, now covering all six engines instead of one. |
| `fast_decode(url)` | `service/providers.py` | Delegate to `runner_registry.fast_decode()`; the duplicated body is deleted. The `link4m`/`bbmkts`/`trafficvn` loop-rejection filter moves into the registry implementation verbatim so `/api/v1/bypass` keeps rejecting those as destinations. |
| `normalize(url)` | `service/providers.py` | Unchanged (already correct); kept local so `service/` has no hard import-time dependency on `src/core` for a string helper. |
| `_do_bypass(url, wait, timeout, client)` | `service/app.py` | **Unchanged** except one line: the fast-path branch is now reachable for all providers (it already calls `fast_decode`, which is now the registry's). No request/response schema change. |
| `dispatchUrl(url, headless)` | `src/ui/menu.js` | Async; classify through the cached `--list` host map (falling back to a `python -m src.bypass_api --list --url <u>` call on a miss), then `runEngine(url, key, headless)`; `OCTOLINK` still branches to the existing in-process `runBypassOctolink`. |
| `runBypassOctolink(targetUrl, headless)` | `src/ui/menu.js` | Kept (only provider with live progress callbacks), but its result rendering goes through the shared `showResultCard()` and `res.reason` is the failure message — unchanged output. |
| `main()` | `src/ui/menu.js` | Menu options 2–6 pass a canonical engine key into `runEngine()` instead of calling the deleted `runBypassXxx` helpers; the hidden `beta`/`trafficvn` path stays and works for both spellings via the alias map. |
| `formatLogLine(rawLine)` | `src/ui/menu.js` | **Unchanged** — deliberately. Its ~20 regex branches match engine log strings; keeping those strings byte-identical is why the plan routes rather than reforms the engines. |

### Removed functions

| Function | File | Migration strategy |
|---|---|---|
| `runBypassLink4M`, `runBypassBBMKTS`, `runBypassGtraffic`, `runBypassLayMa`, `runBypassTrafficVN` | `src/ui/menu.js` | `runEngine(url, key, headless)` → `python -m src.bypass_api --url … --json`, stdout still piped through `formatLogLine()`. |
| `isLink4mUrl`, `isBbmktsUrl`, `isGtrafficUrl`, `isLaymaUrl`, `isTrafficvnUrl` | `src/ui/menu.js` | `detectEngine()` → `runner_registry.classify()` over the cached `--list` payload. `isOctolinkUrl` is retained for the in-process node path. |
| inline BBMKTS `/go/file/` base64 decoder + `>>> http … <<<` matcher | `auto_bypass.py` | `BBMKTSRunner.pre_flight()` already implements the identical logic (unquote, then dynamic-pad base64, with the `bbmkts.com/go/file/` self-reference guard). |
| inline GTraffic `client|dr-client.gtraffic.io/api/url/get` probe | `auto_bypass.py` | `GTrafficRunner.pre_flight()` already implements it verbatim, including `data_link` as dict/str. |
| inline `/go/file/` + query-param base64 fast path | `src/cli.py` | `runner_registry.fast_decode()`. |
| `PROVIDERS` dict and the body of `fast_decode()` | `service/providers.py` | `provider_table.PROVIDER_TABLE` + `runner_registry.fast_decode()`. |
| third host-table copy in `determine_best_engine` | `src/core/brain.py` | `runner_registry.classify()` (kept as a mapping to `"LINK4M"` for `GENERIC`). |
| `_check_response` local helper in the unused `service/app.py` fast path | — | **Not present**; recorded here only so the reviewer knows the plan intentionally leaves `bypass.py`'s engine-local `is_valid_destination()` in place. It is kept, with a one-line comment stating that its `AD_DOMAINS` list must stay in sync with `BaseBypassRunner.BLOCKED_DESTINATION_PATTERNS` (they differ today: `bypass.py` lacks `layma.net`, `yeumoney.com`, `javascript:`; `base_runner.py` lacks `katfile`-style entries — the plan does **not** change either list, since both are engine-specific calibration). |

## [Classes]

### New classes

| Class | File | Key methods | Notes |
|---|---|---|---|
| `EngineKind(str, Enum)` | `src/core/provider_table.py` | `BROWSER`, `EXTERNAL_NODE`, `DECODE` | `str` mixin so it JSON-serialises into `--list` payloads without a custom encoder. |
| `ProviderSpec` (`@dataclass(frozen=True)`) | `src/core/provider_table.py` | fields only (`key`, `aliases`, `hosts`, `url_pattern`, `kind`, `runner`, `module`, `ready`) | Frozen so the table cannot be mutated at runtime by a face. `runner` is a **type reference resolved lazily**: `PROVIDER_TABLE` entries store the class object only after `runners.py` has been imported; to avoid the cycle, the table stores `module` + `runner_key` (`"BBMKTS"`) and `runner_registry.spec_runner(spec)` resolves it through `get_runner(spec.key)`. This keeps `provider_table.py` import-free of `runners.py` while the public `ProviderSpec.runner` accessor stays usable for callers that already imported the registry. |

### Modified classes

| Class | File | Specific modifications |
|---|---|---|
| `BypassResult` | `src/core/base_runner.py` | Add `provider: Optional[str] = None`, `cached: bool = False`, `stage: Optional[str] = None`; extend `to_dict()` with all three. Existing field order/names and `metadata["fast_path"]` semantics unchanged — `test_template_run_fastpath` asserts `success`, `destination_url`, `engine`, `metadata["fast_path"]`. |
| `BaseBypassRunner(ABC)` | `src/core/base_runner.py` | Add class attrs `provider_key: str = "UNKNOWN"` and `standalone_browser: bool = True`. `run()` gains the `standalone_browser` branch (no `BrowserPool.acquire_context()` / no `managed_page.close()` when standalone — the engines own their browsers), stamps `provider`/`stage` on every return path, and keeps the `pre_flight` → `execute_flow` order and the `_check_response` fast-exit interceptor for engines that do pass a page. `is_valid_destination()` and `BLOCKED_DESTINATION_PATTERNS` are unchanged. |
| `BBMKTSRunner` | `src/core/runners.py` | Add `provider_key = "BBMKTS"`; `execute_flow` delegates to `engine_adapters.run_bbmkts`. `pre_flight` body **unchanged** (it is already the canonical implementation the plan consolidates onto). |
| `GTrafficRunner` | `src/core/runners.py` | Add `provider_key = "GTRAFFIC"`; `execute_flow` delegates to `engine_adapters.run_gtraffic`. `pre_flight` unchanged (probe timeout stays 3 s as today; `auto_bypass.py`'s inline copy used 4 s — the 3 s value in `runners.py` wins, and the difference is noted in the commit message as an intentional tightening). |
| `Link4MRunner` | `src/core/runners.py` | Add `provider_key = "LINK4M"`; `execute_flow` picks `run_link4m_cdp` (when `L4M_ENGINE=cdp`) or `run_link4m_legacy`; the CDP branch extracts the alias via `runner_registry.parse_key(target_url)`. `pre_flight` unchanged. |
| `LayMaRunner` | `src/core/runners.py` | Add `provider_key = "LAYMA"`; `execute_flow` delegates to `engine_adapters.run_layma`. No `pre_flight` (inherited `None`). |
| `OctoLinkRunner` | `src/core/runners.py` | Add `provider_key = "OCTOLINK"` and `standalone_browser = False` (it shells out to node; no in-process page needed, but it also must not open a Python browser). `execute_flow` delegates to `engine_adapters.run_octolink`. `pre_flight` keeps the `decode_link.decode_file_url` attempt. |
| `TrafficVNRunner` | `src/core/runners.py` | Add `provider_key = "TRAFFICVN"`; `execute_flow` delegates to `engine_adapters.run_trafficvn`. No `pre_flight`. |
| `FlowDirector` | `src/core/brain.py` | `determine_best_engine()` delegates to the registry; `plan_sponsor_strategy()`, `should_fast_track_api()` and `handle_stage_failure()` are untouched (they operate on sponsor candidates, not providers). |
| `DataController` | `src/core/brain.py` | Untouched. `start_session(url, category)` now receives canonical keys (`OCTOLINK` instead of `LINK999`) — `data/bot_brain.json` profiles keyed on the old spelling are read-through-compatible because `BotBrain.prioritize_candidates`/`get_domain_profile` key on sponsor domains, not on the engine key. A one-time key migration is **not** required; the plan records the naming change in the commit message instead. |
| `Store` | `service/store.py` | Untouched schema. `jobs.provider` / `cache.provider` now hold lowercase canonical keys for all providers; `cache_get(provider, key, ttl)` keys therefore change from `("link4m", alias)` to the same string for Link4M, so existing cache rows stay valid. No migration. |
| `WorkerPool` | `service/worker.py` | `start()` gates `ensure_chrome()` on `L4M_ENGINE == "cdp"`; `_run_job()` drops the provider gate and dispatches through the registry. `submit()` / `wait()` / `_resolve()` / queue sizing untouched. |
| `match`/`Match` | `service/providers.py` | Dataclass untouched; produced by the new wrapper `parse()`. |
| `Menu` state (module-level `currentHeadless`, `runEngine` helpers) | `src/ui/menu.js` | `currentHeadless` untouched; new module-level `ENGINE_LIST_CACHE = null` holds the `--list` payload (host map + engine keys) resolved once at `main()` start-up and reused by `dispatchUrl()` / `detectEngine()`. |

### Removed classes

None. `PROVIDERS` in `service/providers.py` is a dict, not a class; its removal is recorded in Files/Removed functions. No runner class is removed — all six existing registrations survive, which is what `test_runner_registry_lookup` requires.

## [Dependencies]

### No new dependencies

The registry, the table, the adapters and `src/bypass_api.py` are pure standard library (`re`, `json`, `enum`, `dataclasses`, `subprocess`, `urllib.parse`, `argparse`, `base64`, `os`, `pathlib`). Nothing is added to `requirements.txt`, `service/requirements.txt` or `package.json` dependencies.

### Existing dependencies and what this plan requires of them

| Dependency | Current declaration | Requirement |
|---|---|---|
| `playwright>=1.40.0` | `requirements.txt` | Already installed in `.venv` (verified: `import fastapi, playwright` succeeds). `src/core/config.py` prefers `patchright`, falls back to `playwright`; both branches must keep working — adapters import engines, never the browser layer. |
| `patchright>=1.62.0` | `requirements.txt`, `service/requirements.txt` | Unchanged. `bypass.py`, `browser_pool.py`, `link4m_engine.py` prefer patchright; `base_runner.py` already carries the try/except chain. |
| `fastapi>=0.110`, `uvicorn>=0.27` | `service/requirements.txt` | Unchanged. `service/providers.py` gains a `sys.path` bootstrap (same pattern as `service/worker.py` lines 18–21) so it can import the registry; no app-level dependency change. |
| `rapidocr_onnxruntime`, `onnxruntime`, `faster-whisper`, `ddddocr` | `requirements.txt` | Unchanged. The registry never imports solver/OCR modules; they stay behind the engines' lazy imports so `--list` and classification stay instant and light. |
| `discord.js ^14.27.0`, `puppeteer-core ^22.0.0`, `javascript-obfuscator ^5.9.0`, `dotenv ^18.0.4` | `package.json` | Unchanged. `menu.js` loses five `child_process.spawn` call sites but keeps `spawn`/`execSync` for the single `runEngine` path and the Windows clipboard helpers. |
| Node runtime | v26.13.1 on this box | Sufficient for `octolink_runner.js` (`module.exports = { runBypass }`) and `dist/core.bundle.js`. |
| Python runtime | 3.13.5 system + `.venv/` | Sufficient. No 3.11-only syntax is introduced; `service/*` already uses `from __future__ import annotations` for its `X | None` annotations. |

### Cross-module integration requirements

1. **`sys.path` bootstrap ordering.** `runner_registry.py` must insert `src/core` into `sys.path` at import time (the pattern `bypass.py` uses at lines 4–9) so flat imports (`from base_runner import …`, `import engine_adapters`) resolve when imported from `auto_bypass.py`, `src/cli.py`, `src/bypass_api.py` and `service/*`.
2. **Import-side-effect hygiene (hard requirement).** `bypass.py` calls `ensure_python_runtime()` at import (line 12), which can `subprocess.run` and `sys.exit()` into another interpreter. The registry must therefore **never** import `bypass` at module scope — only inside `engine_adapters.run_link4m_legacy()` / `run_link4m_cdp()`. A top-level import would let a bare `python -m src.bypass_api --list` re-exec the process.
3. **Chrome isolation.** `link4m_engine.ensure_chrome()` and `/usr/bin/google-chrome` on `:9222` are only needed for `L4M_ENGINE=cdp`. `service/worker.py` must not boot Chrome for non-Link4M-only deployments.
4. **Node availability.** `run_octolink` raises `DestinationNotFound` (never `FileNotFoundError`) when `node` is missing, preserving `OctoLinkRunner`'s existing error semantics.
5. **Docs alignment (no code impact).** `README.md`, `PROJECT.md`, `TEST_INFRA.md` and `API_DOCUMENTATION.md` reference Python 3.11 and Windows absolute paths (`C:\Users\XUAN\…`). This plan does not rewrite them; the PR description must state the canonical provider keys and the new `src.bypass_api` entry so the docs can follow.

## [Testing]

### Test file matrix

| File | Status | Requirement |
|---|---|---|
| `tests/test_provider_registry.py` | **new** | Offline registry contract suite (functions listed in [Functions]). Script-style `if __name__ == "__main__"`, matching `tests/test_fast_paths_and_pool.py`. No network, no browser, no Node. |
| `tests/test_engine_adapters.py` | **new** | Offline adapter/normaliser suite; stub engine modules injected into `sys.modules`, `subprocess.run` stubbed. |
| `tests/test_fast_paths_and_pool.py` | **modified, minimal** | The three existing tests must keep passing **unmodified** — they are the regression guard for the registry rewrite. Only addition permitted: `get_runner("link999")` returns `OctoLinkRunner` (alias lookup). |
| `tests/test_unit_core.py` | **modified** | `test_classify_url` case `("https://octolink.vip/abc", "LINK999")` → `"OCTOLINK"`. `test_clean_destination_url`, `test_unmask_domain_candidates` and the storage assertions untouched. |
| `tests/test_suite_integrity.py` | **modified** | Same `LINK999` → `OCTOLINK` expectation update in its classifier table. |
| `tests/test_tier1_strip_vision.py` … `test_tier5_cli_api.py`, `tests/test_r3_cli_api.py`, `tests/adversarial_cli_api_stress.py` | **unmodified, must pass** | They assert the CLI/API contract (`python -m src.cli --url …` JSON shape, `/api/bypass` payload). This plan preserves those contracts exactly; a failure here is a regression, never a test edit. |
| `tests/test_playwright_bypass.py` and any live-network test | **gated** | Runs only with `RUN_LIVE=1`; default invocation must skip cleanly (they are already effectively skipped on this box, which has no network). |

### Validation strategy

**Tier 0 — static/import gate (fastest; must be green first):**

```bash
.venv/bin/python -c "import sys; sys.path.insert(0,'src/core'); import runner_registry; print(runner_registry.supported())"
.venv/bin/python -m src.bypass_api --list | python3 -m json.tool
node -e "require('./src/ui/menu.js')"
python3 -c "import ast; [ast.parse(open(f).read()) for f in ['auto_bypass.py','src/cli.py','src/bypass_api.py','src/core/runner_registry.py','src/core/provider_table.py','src/core/engine_adapters.py','src/core/runners.py','src/core/base_runner.py']]"
```

`--list` must complete without importing `bypass` (check `sys.modules` in the test), proving requirement #2 of the Dependencies section holds.

**Tier 1 — offline unit/contract (primary gate):**

```bash
.venv/bin/python tests/test_provider_registry.py
.venv/bin/python tests/test_engine_adapters.py
.venv/bin/python tests/test_fast_paths_and_pool.py
.venv/bin/python tests/test_unit_core.py
.venv/bin/python tests/test_suite_integrity.py
```

Each prints its own `[PASS]` / `ALL … PASSED` banner and exits 0 — repo convention. The runner stays plain `python`: there is no `pytest.ini`, `setup.cfg`, `tox.ini` or `pyproject.toml` in the tree, so no test tooling is introduced.

**Tier 2 — face-convergence smoke, offline (this is the actual acceptance criterion of the whole plan):**

```bash
# 1. registry itself
.venv/bin/python -c "import sys;sys.path.insert(0,'src/core');import runner_registry as r;print(r.classify('https://link999.app/x'), r.classify('https://bbmkts.com/go/3p82s'), r.classify('https://trafficvn.com/get/MFGm2tAlcSn'), r.classify('https://unknown/x'))"
# 2. auto_bypass
.venv/bin/python -c "import sys;sys.path.insert(0,'.');import auto_bypass as a;print(a.classify_url('https://octolink.vip/abc'))"
# 3. brain
.venv/bin/python -c "import sys;sys.path.insert(0,'src/core');import brain;b=brain.get_brain();print(b.flow_director.determine_best_engine('https://gtraffic.io/X3BR2OQ'))"
# 4. service providers
.venv/bin/python -c "import sys;sys.path.insert(0,'service');sys.path.insert(0,'src/core');import providers;print(providers.supported());print(providers.parse('https://link4m.net/go/2kCcIqn'))"
```

All four must agree on the same canonical keys — a disagreement is precisely the bug this plan removes. Expected: `OCTOLINK`, `BBMKTS`, `TRAFFICVN`, `GENERIC`; `OCTOLINK`; `GTRAFFIC`; `['bbmkts','gtraffic','layma','link4m','octolink','trafficvn']` + a `Match`.

**Tier 3 — service integration, offline and browserless (proves `service/` is no longer Link4M-only):**

```bash
DB_PATH=/tmp/l4m_test.db SERVICE_LOG=/tmp/l4m_test.log CLEAR_PROXY=1 API_KEY= \
  .venv/bin/python -m uvicorn service.app:app --host 127.0.0.1 --port 8099 &
curl -s http://127.0.0.1:8099/health
curl -s http://127.0.0.1:8099/api/v1/supported
curl -s "http://127.0.0.1:8099/api/v1/bypass?url=https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS94&wait=1"
```

The last call must return `status=success` with destination `https://example.com/x` — a pure DECODE/pre-flight resolution needing no network, no Chrome and no Node. It is the single strongest end-to-end proof that the queue → registry → runner → fast-path chain is wired.

**Tier 4 — live end-to-end (opt-in, `RUN_LIVE=1`, documented demo links only):** one URL per engine, taken from the existing menu defaults — `link4m.net/go/2kCcIqn`, `bbmkts.com/go/3p82s`, `gtraffic.io/X3BR2OQ`, `layma.net/pohWNZgba`, `octolink.vip/K3r4k5`, `trafficvn.com/get/MFGm2tAlcSn` — asserting `res.success`, `res.destination_url` matching no `BLOCKED_DESTINATION_PATTERNS` entry, and `res.provider ==` the expected canonical key. Requires network + Chrome + Node; never part of the default run.

### Regression discipline

`tests/test_fast_paths_and_pool.py` is treated as a frozen contract (`success`, `destination_url`, `engine`, `metadata["fast_path"]`, `isinstance(get_runner(...))`). If a change breaks it, the change is wrong, not the test. Likewise the CLI/API JSON contracts in the tier tests must not need edits — the whole plan is built so they don't.

## [Implementation Order]

Ordered so every step leaves the tree runnable and the frozen contracts green. Steps 1–4 build the registry without touching any face; steps 5–9 migrate one face at a time, each independently revertible.

1. **`src/core/provider_table.py` (new).** `EngineKind`, `ProviderSpec`, `PROVIDER_TABLE`, `PROVIDER_ALIASES`, `GENERIC_KEY`, `spec_for()`, `canonical_key()`. No import from `runners.py`. Verify: import standalone, assert 7 specs and `spec_for("link999").key == "OCTOLINK"`.

2. **`src/core/engine_adapters.py` (new).** `dest_from()` + the seven `run_*` shims with lazy engine imports. Add the `--json` trailing `JSON.stringify({success, finalUrl, reason})` line to `src/core/octolink_runner.js` (all existing log lines preserved) because `run_octolink` depends on it. Verify: `tests/test_engine_adapters.py`.

3. **`src/core/base_runner.py` (modify).** Additive `BypassResult` fields + `to_dict()`; `provider_key`, `standalone_browser`, and the `run()` branch that skips `BrowserPool`. Verify: `tests/test_fast_paths_and_pool.py` green (it exercises `run()` via `test_template_run_fastpath`).

4. **`src/core/runner_registry.py` (rewrite) + `src/core/runners.py` (modify) + `src/core/__init__.py` (bootstrap).** Wire table → runners; add `detect`/`classify`/`normalize_key`/`supported`/`parse_key`/`fast_decode`/`execute`; alias-aware `get_runner`; delegating `execute_engine`; add `provider_key`/`standalone_browser` + adapter delegation to all six runners. Verify: `tests/test_provider_registry.py` + `tests/test_fast_paths_and_pool.py`. First complete-but-unused checkpoint — safe to commit.

5. **`src/bypass_api.py` (new).** `build_parser` / `list_payload` / `run_once` / `emit_result` / `main`. Verify Tier 0 (`--list` without importing `bypass`) and a pre-flight-only run (`bbmkts /go/file/<b64>` → exit 0, `FINAL DESTINATION URL:` on stdout).

6. **`src/cli.py` (modify).** Route `resolve_bypass()` through the registry; add `--engine` / `--list`; keep the JSON-stdout contract. Verify: `tests/test_r3_cli_api.py`, `tests/test_tier5_cli_api.py`, `tests/adversarial_cli_api_stress.py` — all untouched.

7. **`auto_bypass.py` + `src/core/brain.py` (modify).** `classify_url()` and `execute_bypass()` and `FlowDirector.determine_best_engine()` all delegate to the registry (`GENERIC`→`LINK4M` mapping kept in brain). Update the `LINK999`→`OCTOLINK` expectations in `tests/test_unit_core.py` and `tests/test_suite_integrity.py` in the same change. Verify both files plus an `auto_bypass.py --json` run on a pre-flight-resolvable URL.

8. **`service/*` + `src/core/link4m_engine.py` (modify).** Provider wrappers over the registry; drop the Link4M-only gate; gate `ensure_chrome()` on `L4M_ENGINE`; replace the `~/Link4M-Bypass-Suite` `REPO` constant with a `__file__`-relative one in all four files. Verify Tier 3.

9. **`src/ui/menu.js` + `bot_discord.js` (modify).** Delete the five `runBypassXxx` blocks and five predicates; add `runEngine()` / `detectEngine()` / `ENGINE_LIST_CACHE`; keep `runBypassOctolink` in-process; switch the bot to the `__BYPASS_JSON__` line and generate `/platforms` from `--list`. Verify: `node -e "require('./src/ui/menu.js')"`, a scripted menu run against a pre-flight URL (stdout still formatted by the untouched `formatLogLine`), and `node --check bot_discord.js`.

10. **`package.json` scripts + PR description.** Add `bypass` / `list` scripts; record canonical keys, the `LINK999`→`OCTOLINK` rename, the `src.bypass_api` entry, the `L4M_ENGINE`/`L4M_REPO` env vars, and the GTraffic pre-flight timeout tightening (4 s → 3 s). Run the full Tier 0–3 sweep before handoff.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| `bypass.py`'s import-time `ensure_python_runtime()` re-execs the process if imported at registry scope. | Hard rule in steps 2 and 4: engines are imported only inside adapter function bodies. Tier 0 asserts `"bypass" not in sys.modules` after `--list`. |
| Double browser / pooled-context leak (a latent bug today — `BaseBypassRunner.run()` acquires a pooled context, then every engine launches its own browser). | `standalone_browser = True` default plus the `run()` branch in step 3; `OctoLinkRunner` sets it `False` explicitly. |
| `menu.js` log-formatting breakage from changed engine output. | Engine log strings are never edited, `formatLogLine()` is explicitly out of scope, and step 9 keeps piping raw engine stdout into it. |
| Silent behaviour change for unknown hosts (registry returns `GENERIC`; engines historically defaulted to Link4M). | The registry never defaults. `auto_bypass.execute_bypass()` and `brain.determine_best_engine()` keep their explicit Link4M fallback, so user-visible behaviour is identical. |
| Service cannot boot from any path other than `~/Link4M-Bypass-Suite`. | `REPO` becomes `__file__`-relative with an `L4M_REPO` override, in one step (8) across all four affected files. |
| OctoLink result race through `destination_url.txt`. | Replaced by stdout JSON parsing in the adapter; the file read is deleted from `runners.py`. |
| Two different destination blocklists exist (`bypass.py` `AD_DOMAINS` vs `BaseBypassRunner.BLOCKED_DESTINATION_PATTERNS`) and have already drifted. | Deliberately untouched — each is engine-specific calibration. A cross-reference comment is added; reconciling them is a separate task with its own live-test requirement. |
| Scope creep into the duplicated `scripts/*.py` copies and the ~90-file test sprawl. | Explicitly out of scope; listed in Files as a follow-up so this change stays reviewable and revertible. |

### Acceptance checklist (definition of done)

- `tests/test_fast_paths_and_pool.py`, `tests/test_unit_core.py`, `tests/test_suite_integrity.py` green, with only the documented `LINK999`→`OCTOLINK` edits.
- The tier CLI/API tests (`test_r3_cli_api.py`, `test_tier5_cli_api.py`, `test_tier1..4`) pass **with no edits to those files**.
- `tests/test_provider_registry.py` and `tests/test_engine_adapters.py` green, fully offline.
- All four faces classify every supported host identically (Tier 2), and `service/` answers `/api/v1/supported` with six providers and resolves a BBMKTS `/go/file/` link without network, Chrome or Node (Tier 3).
- `python -m src.bypass_api --list` imports no engine module and never imports `bypass`.
- Exactly one dispatch call site (`runner_registry.execute()`) serves `auto_bypass.py`, `src/cli.py`, `src/bypass_api.py` and `service/worker.py`; `menu.js` and `bot_discord.js` reach it only through `src/bypass_api.py`.
---

## [Addendum] Live benchmark baseline — 2026-11-24

Measured on this box (Python 3.13.5 + `.venv`, Chrome 158 on CDP `127.0.0.1:9222` with `--no-proxy-server`, Node v26.13.1, network up). One link, as requested: `https://link4m.net/go/2kCcIqn` via the proven engine `src/core/link4m_engine.py 2kCcIqn --json`.

### Result — success on run 3 (clean run, stale artifacts quarantined first)

| Metric | Value |
|---|---|
| Wall clock | **6 m 45 s** (engine log line 702 at `18:46:56` → last write `18:53:41`) |
| Stage: campaign load + OCR | `18:46:56 → 18:47:0x` — campaign `6b0157bfe50516c54d0da856`, **ảnh 3** (OCR path, not cache) |
| Stage: sponsor hunt | `18:46:56 → 18:50:03` ≈ **3 m 07 s**, 20 candidate URLs fetched, 12 passed the widget check, 1 chosen |
| Stage: quest | `18:50:03 → 18:53:41` ≈ **3 m 38 s** (page open 18:51:34, 60 s timer 1/2, reload, 14 s timer 2/2) |
| Stage: captcha | `18:53:30 → 18:53:32` ≈ **2 s**, instant tier, token length 2425, no image grid needed |
| Sponsor used | `https://keobongda1.tv` (discovered from the OCR'd instruction image) |
| Code extracted | `DTsiYu` |
| Destination | `https://dash.nvnmc.cloud/earn/callback/5ba6d341f33b188e7aaa8a686ee9909126d21f398644cc75717695748364f861` |
| Artifact proof | `destination_url.txt` + `logs/last_run.json`, both mtime `18:53`, written after the pre-run quarantine |

Fast paths (offline, no browser, measured):

| Path | Time |
|---|---|
| `BBMKTSRunner.pre_flight()` on `/go/file/<b64>` | **0.020 – 0.050 ms** |
| `Link4MRunner.pre_flight()` on `?url=<b64>` | instant (`< 1 ms`) |
| `BaseBypassRunner.run()` template, pre-flight branch | 0.02 ms, `metadata["fast_path"] = True` |
| `tests/test_fast_paths_and_pool.py` | 4/4 pass, exit 0 |

### Failures observed (and what they change in the plan)

1. **Run 1 (`timeout 280`) was killed mid-quest** after trying `tylekeo1.in` twice (that sponsor had no `LẤY MÃ` button). Conclusion: the engine genuinely needs ≥ 480 s — this is exactly why `service/config.py` already sets `JOB_TIMEOUT = 480`. **Plan change:** Tier 4's live runner and any new façade (`src/bypass_api.py`) must default to a 480 s budget, never the CLI's 60 s.
2. **Run 2 died in 45 s** with `RuntimeError: Chrome CDP không mở được sau 45s`. `ensure_chrome()` kills a proxied Chrome and relaunches it, then allows only 45 s for the first cold start — which the relaunch exceeded. **Plan change:** step 5/8 must pre-warm Chrome (`link4m_engine.ensure_chrome()`) before the first `execute()` in `src/bypass_api.py` and `service/worker.py`, and `bypass_api` should surface a distinct `ERR_BROWSER_CRASH` instead of letting the raw `RuntimeError` escape.
3. **Stale-artifact hazard (new finding, now in scope for step 8).** Before these runs, `destination_url.txt` (mtime `05:54`) and `logs/last_run.json` (mtime **the previous day, 22:56**) already contained a *successful* result for the same alias — indistinguishable from a fresh win without checking mtimes. `config.save_destination()` already supports run-scoped files via `BYPASS_RUN_ID` → `destination_url-<id>.txt`, but **`link4m_engine.py` ignores it** and writes the fixed paths directly (`DEST_FILE`, `RESULT_FILE`). **Plan change:** step 8 must route `link4m_engine.py`'s writes through `config.save_destination(..., run_id=os.environ.get("BYPASS_RUN_ID"))` / a run-scoped `last_run-<id>.json`, so four faces hitting the same box can never read each other's stale result. This is the single most valuable finding of the benchmark.
4. **Response capture is flaky, resolution is not.** Run 3 logged `[server] không bắt được response` (`server: ""`), while the previous day's run caught the API JSON (`"Kiểm tra mật khẩu thành công"`). The destination was still resolved from the `.get-link` href, so the outcome is unchanged — but it confirms the plan's choice to keep `is_valid_destination()` on the button-href path as a first-class capture route, not a fallback afterthought.

### Plan impact summary

No change to the [Types], [Files] or [Functions] designs. Three concrete amendments: (a) 480 s default budget on every ≥ browser path; (b) pre-warm Chrome + distinct browser-crash error code; (c) run-scoped result files in `link4m_engine.py` via the existing `BYPASS_RUN_ID` mechanism. Tiers 0–3 of [Testing] remain the offline gate; Tier 4 now has a measured baseline (≈ 6 m 45 s, single worker) to compare against.


---

## [Handoff] 2026-11-25 — steps 1–10 closed, offline gate green

Trạng thái sau khi hoàn tất trục registry:

- Bước 1–9: xong. `provider_table.py`, `engine_adapters.py`, `bypass_api.py`,
  `runner_registry.py` là nguồn duy nhất; `auto_bypass.py`, `src/cli.py`,
  `service/*`, `src/ui/menu.js`, `bot_discord.js` chỉ còn gọi registry.
- Bước 10: xong. `package.json` có `list` / `bypass` / `check`; tài liệu ở
  `docs/UNIFIED_DISPATCH.md` (canonical keys, entry points, `L4M_ENGINE`,
  `L4M_REPO`, `BYPASS_RUN_ID`, `JOB_TIMEOUT`).
- Addendum (a): ngân sách 480 s là mặc định ở `bypass_api.DEFAULT_TIMEOUT`
  và `service/config.JOB_TIMEOUT`.
- Addendum (b): `bypass_api.run_once()` pre-warm Chrome khi `L4M_ENGINE=cdp`
  và trả `ERR_BROWSER_CRASH` thay vì để `RuntimeError` thoát ra.
- Addendum (c): `link4m_engine.py` ghi qua `save_destination()` /
  `save_result()`; mỗi lần chạy có `destination_url-<BYPASS_RUN_ID>.txt` và
  `logs/last_run-<BYPASS_RUN_ID>.json`, bản cố định vẫn được ghi để menu đọc.
- `config.save_destination()` chỉ ghi file Desktop trên Windows; trước đó trên
  Linux nó tạo file rác tên `~\Desktop\destination_url.txt` ngay trong repo.

Kết quả đo offline (máy này, không mạng, không browser):

| Gate | Kết quả |
|---|---|
| `tests/test_provider_registry.py` | PASS |
| `tests/test_engine_adapters.py` | PASS |
| `tests/test_fast_paths_and_pool.py` | PASS |
| `tests/test_unit_core.py` | PASS |
| `tests/test_suite_integrity.py` | PASS |
| `python -m src.bypass_api --list` | rc=0, `bypass` không nằm trong `sys.modules` |
| `service/app.py` `/api/v1/supported` | 200, sáu provider |
| `POST /api/v1/bypass` với BBMKTS `go/file/<b64>` | 200, `provider=decode`, 0.1 ms |
| `node --check` menu.js / bot_discord.js / octolink_runner.js | PASS |

Chưa làm (cần mạng/browser, ngoài gate offline): Tier 4 live cho từng provider,
và việc hạ timeout pre-flight GTraffic 4 s → 3 s (giữ nguyên vì chưa đo lại).

## [Handoff] 2026-11-26 — Tier 4 live: kết quả đo, và engine-rs

### engine-rs (native) — `15b4f67`

- `wait_for_page` trước đây coi `#captcha-html-wrapper` trần là "đã sẵn sàng".
  Wrapper đó có cả trên trang khung chiến dịch trước khi form mã render, nên
  flow giải captcha 4 lần (token 2382–2510) trong **4 m 55 s** rồi vẫn fail vì
  không có mã. Nay chỉ sẵn sàng khi `input[name=password]` hiển thị, hoặc form
  có mặt **và** wrapper có mặt.
- Hệ quả: `--once 2kCcIqn` trên campaign mới trả `needs_code` sau **10 s**
  (release) / 11.8 s (debug) thay vì đốt 5 phút.
- `GET /api/v1/bypass?wait=1` nhận đúng; hàng đợi đầy không còn để lại job
  "running" ma.
- Build sạch cần `WHISPER_DONT_GENERATE_BINDINGS=1` (tránh bindgen/libclang) và
  `cmake` + `g++`; `engine-rs/build.sh` làm sẵn. Release ~3 phút, binary 7.1 MB.
- `--check` OK với Chrome 158: `check ok: chrome + cdp + whisper`, ~18–21 s.
- 14 unit test pass. Chưa có integration test cho HTTP API (cần Asr thật để dựng
  `ApiState`).

### Python full flow — vẫn chưa qua live

Chạy `src/core/link4m_engine.py 2kCcIqn --json` trên box này:

| Lần | Cấu hình | Kết quả |
|---|---|---|
| 1 | không đặt `L4M_HEADLESS` | audio fail → vào chờ lưới ảnh thủ công → timeout 560 s |
| 2 | `L4M_HEADLESS=1` | giải audio ra token 2489, `[server] không bắt được response`, rồi chuyển sang quét sponsor (OCR `tylekeopro.site`) → timeout 420 s |

Kết luận: phần quest/sponsor + submit vẫn là chỗ hỏng, không phải phần nhận diện
trang. Đây là lý do engine native chỉ chạy fast path và trả `needs_code`; muốn
native chạy trọn link mới cần port quest (chọn sponsor → OCR ảnh hướng dẫn →
lấy mã → countdown) sang Rust.

## [Handoff] 2026-11-26 (2) — GTraffic pre-flight 4 s → 3 s, đo lại

Đo `resolve_sponsor_domain()` trên box này, 2026-11-26, bằng cách bọc
`urllib.request.urlopen` để lấy thời gian từng candidate:

| Candidate | Kiểu | Thời gian |
|---|---|---|
| `kitu360.com` | sống | 0.98 s |
| `ericly.net` | sống | 0.64 s |
| `thoitiethomnay.org` | sống | 0.48 s |
| `timvanphong.com.vn` | sống | 0.28 s |
| `bongda686.in.net` | chết (DNS) | 0.011 s |
| `hitclub.cards` | chết (DNS) | 0.011 s |
| `example.com` | sống, không phải sponsor | 0.13 s |

Kết luận: candidate sống trả trong **≤ 1.0 s**; host chết fail gần như tức thì.
Timeout chỉ cắt được trường hợp TCP mở mà không trả lời. Hạ ceiling xuống
**3.0 s** (`_PREFLIGHT_TIMEOUT`) vẫn còn 3x headroom, tiết kiệm 1 s cho mỗi
candidate bị treo. Đã áp và đo lại: `kitu360.com` 0.76 s, `timvanphong.com.vn`
0.59 s, `ericly.net` 0.51 s — không hồi quy.

Ghi chú: 14 s của một lượt miss (`bongda686.in.net`) **không** nằm ở pre-flight
fetch mà ở `fallback_ai_search` → `resolve_domain_gemini_ai` →
`ask_mimo_free`: daemon MiMo poll ~28 × 0.5 s rồi mới fallback. Nếu muốn cắt
thật thì cắt ở đó (cho phép tắt MiMo khi pre-flight, hoặc hạ `max_wait`), không
phải ở timeout fetch. Chưa đổi vì ngoài phạm vi mục addendum (a).

### Ghi chú các file Python đã có sẵn trong working tree

Sáu file sửa ngoài phiên (`bbmkts_runner.py`, `captcha_audio.py`, `fast_decode.py`,
`gtraffic_runner.py`, `link4m_engine.py`, `runners.py`) đã được đọc và chạy qua
gate offline — giữ nguyên, commit cùng lượt này:

- Desktop copy chỉ ghi khi `os.name == "nt"` (trước đó tạo
  `~/Desktop/destination_url.txt` trong repo trên Linux ở cả BBMKTS/GTraffic).
- `fast_decode`: cho phép `~` và `%` trong `/go/file/<b64>`; chỉ nhận
  `http://`/`https://` thay vì prefix `http` bất kỳ.
- `runners.Link4MRunner`: `L4M_ENGINE` mặc định là `cdp` (đi qua registry), chỉ
  `legacy` mới dùng flow cũ.
- `captcha_audio`: dò lại `bframe` sau khi đổi chế độ audio thay vì giữ tham
  chiếu frame cũ; nhận diện "try again later"/"automated"/"blocked" là bị chặn.
- `link4m_engine.submit`: ô mã dò rộng (`#main-form-3`, `form input[name=password]`
  …), hỗ trợ vào thẳng bước captcha khi phiên trước đã nhập mã, reload lấy anchor
  mới khi thử thách hỏng, bấm `.get-link` khi nút đã hết disabled; headless bỏ
  lưới ảnh thủ công trừ khi `L4M_MANUAL_GRID=1`.

Gate sau khi áp: `test_fast_paths_and_pool`, `test_provider_registry`,
`test_engine_adapters`, `test_suite_integrity`, `test_unit_core`, `test_r3_cli_api`
— tất cả PASS.

## [Handoff] 2026-11-26 (3) — Tier 4 live: link demo đã chết, và launch fix GTraffic

### Kết quả chạy live qua `src.bypass_api` (budget 420 s)

| Provider | Link | HTTP | Kết quả | Nguyên nhân |
|---|---|---|---|---|
| Link4M | `link4m.net/go/2kCcIqn` | 200 | `needs_code` sau ~10 s (engine native); Python quest fail sau 420–560 s | quest/sponsor chưa xong ở bản Python; native chỉ fast-path |
| BBMKTS | `bbmkts.com/go/3p82s` | 200 | `ERR_DESTINATION_NOT_FOUND` sau 101 s | Cloudflare Turnstile không giải được: Ocilar API `api.ocilar.com` bị proxy chặn (502) và timeout |
| GTraffic | `gtraffic.io/X3BR2OQ` | 200 → `/404` | `ERR_DESTINATION_NOT_FOUND` sau 20 s; **trước đó chết ngay ở launch** | link demo hết hạn (server trả trang 404); launch fix bên dưới |
| LayMa | `layma.net/pohWNZgba` | 200 | `ERR_DESTINATION_NOT_FOUND` sau 7 s | campaign id `00000000-…`: link hết lượt/không còn chiến dịch |
| OctoLink | `octolink.vip/K3r4k5` | **404** | không chạy | link demo chết |
| TrafficVN | `trafficvn.com/get/MFGm2tAlcSn` | **404** | không chạy | link demo chết |

Kết luận Tier 4: **không thể** xác nhận success end-to-end bằng bộ link demo
trong plan — 5/6 link đã hết hạn hoặc bị chặn ở tầng riêng. Cần link tươi để
chạy lại; đây là dữ liệu đầu vào, không phải lỗi dispatch. Bằng chứng dispatch
vẫn đúng: mỗi provider được nhận diện đúng key, chạy đúng engine, và báo lỗi
theo đúng `error_code`/`stage` của envelope.

### GTraffic: patchright launch không có browser

`gtraffic_runner.py` nhánh `IS_PATCHRIGHT` gọi `p.chromium.launch(headless=…)`
mà không truyền `executable_path`. Patchright không đóng gói browser, nên trên
box này chết ngay:

```
BrowserType.launch: Executable doesn't exist at
~/.cache/ms-playwright/chromium_headless_shell-1248/...
```

Đã sửa: truyền `executable_path=CHROME_PATH` (khi tồn tại) và `args` như nhánh
playwright. Sau fix, engine vào được trang và chạy hết 3 attempt trước khi báo
link 404. `errexit` của lần chạy trước (4 s) → 20 s, đúng hành vi.

### engine-rs: HTTP contract test + `asr` optional

`Inner.asr` đổi thành `Option<SharedAsr>` để dựng được `ApiState` trong test mà
không cần model 77 MB. Worker trả `kind: "asr"` nếu job chạy khi thiếu model
(chỉ xảy ra trong test). Thêm 5 test HTTP (18 tổng) phủ `/health`,
`/api/v1/supported`, decode POST/GET `wait=1`, 400/501, auth, jobs 404,
batch > 50. `cargo clippy --all-targets` sạch sau khi sửa 4 cảnh báo cũ
(`chunks_exact`, `useless_conversion`, `next_back`, `result_large_err`).

## [Handoff] 2026-11-26 (4) — gate Tier 0–3 chạy đủ trên box này

### Môi trường còn thiếu, đã bổ sung

| Thiếu | Cài | Hệ quả |
|---|---|---|
| `speech_recognition` (có trong `requirements.txt` nhưng chưa cài) | `.venv/bin/pip install SpeechRecognition` → 3.17.0 | `test_tier2_audio_direct.py` từ rc=1 → **rc=0** |
| Playwright chromium/headless-shell | `.venv/bin/playwright install chromium` (v1255, 126 MB) | `test_tier3_hybrid_fallback.py` từ rc=1 → **rc=0** |

Tier 1: rc=0. Tier 2: PASS 100%. Tier 3: PASS 100% (2Captcha token 3.98 s).
Tier 5: rc=0.

### Tier 4 — fixture `adv.json` đã bị purge

`test_tier4_rapidocr_sponsor.py` cần `adv.json` ở repo root, nhưng fixture này
đã bị xoá ở commit `d7de58c` ("purge legacy dump files, scratch tests, and dev
artifacts"). Thử tái tạo từ endpoint thật:

```
POST https://s1.link4m.app/api/campaign/get-advertise
  alias=2kCcIqn&codes=
→ 200 {"success": false, "info": "No Campaign", "code": -1}
```

Alias demo không còn campaign nên không sinh lại được payload có ảnh nhiệm vụ.
Test này là golden-fixture (assert OCR thấy đúng "keo nha cai"/"tylenhacai"),
không phải test hành vi — không sửa test, không bịa fixture. Ghi nhận là gap
đầu vào, cần một capture `adv.json` mới từ campaign sống.

### Xác nhận lại các mặt

- `service/` (Tier 3): `/health` 200, `/api/v1/supported` trả đủ 6 provider,
  `GET /api/v1/bypass?url=bbmkts/go/file/<b64>&wait=1` → `status=success`,
  destination `https://example.com/x`, `elapsed_ms=0.1`, không cần Chrome/Node.
- `server-rs` smoke: **23 PASS / 0 FAIL**, port 8098.
- `engine-rs`: 18 test pass, clippy sạch, release build OK, `--check` OK,
  `--once 2kCcIqn` → `needs_code` sau 9.2 s.
- Cả bốn face gọi đúng một cửa dispatch: `runner_registry.execute()` trong
  `auto_bypass.py:125`, `src/cli.py:89`, `src/bypass_api.py:91`,
  `service/worker.py:32`.

## [Handoff] 2026-11-26 (5) — Turnstile mở được, và vì sao Tier 4 vẫn không qua

### Turnstile solver trước đây không chạy được — không phải do Cloudflare

Ba lỗi chồng nhau, đã sửa:

1. `package.json` **không khai báo `patchright`** dù `turnstile_solver.js` require
   nó → mọi lần gọi Node chết ở `MODULE_NOT_FOUND`, BBMKTS rơi xuống Python rồi
   xuống Ocilar cloud (box này chặn IP `api.ocilar.com`).
2. `chromium.launch` của patchright không có browser (download của patchright bị
   chặn). Solver JS nay dò `CHROME_BIN` → Chrome hệ thống → đường dẫn Windows.
3. `get_turnstile_token()` gọi `sync_playwright()` trong thread đang giữ một sync
   Playwright context (BBMKTS runner) → `Sync API inside the asyncio loop`. Nay
   chạy solve trong thread riêng khi thấy event loop.

Đo lại: Node solver trả token **773 ký tự** sau **22.8 s** độc lập, **16.7 s**
khi gọi từ trong sync Playwright context. Budget Node nâng 25 s → **45 s** vì
25 s cắt ngang cold start và để lại browser mồ côi (EPIPE).

### Tier 4 vẫn không thể xanh trên box này

- `test_tier4_rapidocr_sponsor.py` cần `adv.json` (đã purge ở `d7de58c`).
  Đã lấy được response thật qua `link4m_http.Session(alias).open().advertise()`
  (`success=true`, `html` 3609 ký tự, 1 ảnh base64) — nhưng đó là campaign
  "TRỰC TIẾP", không chứa keyword mà test assert (`keo nha cai`/`tylenhacai`).
  Không bịa fixture.
- Nặng hơn: `requirements.txt` ghi `rapidocr_onnxruntime>=1.3.0` nhưng mirror
  pip của box chỉ có **1.2.3**. Bản 1.2.3 có bug: truyền `det_limit_side_len`
  mà không truyền `det_model_path` → `KeyError: 'model_path'` trong
  `update_det_params`. Test gọi đúng kiểu đó, nên kể cả có `adv.json` test vẫn
  crash ở `setUpClass`. Cần mirror có ≥ 1.3.0 (hoặc wheel tự build) mới chạy.

Tier 1/2/3/5 vẫn xanh sau các thay đổi turnstile.
