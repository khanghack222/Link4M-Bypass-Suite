# Project: Link4M Bypass Suite Next-Gen Solver & SEO Automation

## Architecture
- **Language/Runtime**: Python 3.11 64-bit (`C:\Users\XUAN\AppData\Local\Programs\Python\Python311\python.exe`) + Playwright Chromium.
- **Entry Points**: `auto_bypass.py` -> `src/core/bypass.py` (Autonomous Link4M Runner).
- **Captcha Engine**: `src/core/recaptcha_solver.py` implementing 3-Tier Multi-Resilient Solver:
  - Tier 1: Instant Anchor Check via Trust Score (< 0.5s).
  - Tier 2: Direct JS Audio Event Dispatch + In-Memory Google Speech Recognition (< 2s, 0% CPU, 0$ cost).
  - Tier 3: Cloud Token API Fallback (2Captcha) upon DOSCAPTCHA or rate limit.
  - Zero Vision AI: Complete deprecation of ONNX 57k, YOLOv12x, CLIP, and visual tile classifiers.
- **SEO Traffic Engine**: `src/core/sponsor.py`:
  - Intercepts ad payload from `s1.link4m.app/api/campaign/get-advertise`.
  - RapidOCR decodes Base64 mission images (~50ms CPU).
  - Emulates user scroll pulses to prevent widget stall.
  - Retrieves 6-digit PIN code from sponsor widget and triggers `checkPassword` / `get-link-info` dispatch.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| 1 | Strip Vision Captcha | Decommission YOLOv12x, ONNX 57k, CLIP, and image tile solvers from `recaptcha_solver.py` | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Direct JS Audio Challenge | Implement 1ms Direct JS click on `#recaptcha-audio-button` and in-memory Google Speech Recognition | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Instant Tick Trust Score | Tier 1 instant green checkmark detection via persistent context (< 0.5s) | M2 | ORIGINAL_REQUEST §R2 |
| 4 | Cloud API Fallback | Tier 3 2Captcha fallback when DOSCAPTCHA / rate-limit occurs | M2 | ORIGINAL_REQUEST §R2 |
| 5 | SEO Sponsor Interception | Intercept `s1.link4m.app/api/campaign/get-advertise` and extract mission images | M3 | ORIGINAL_REQUEST §R3 |
| 6 | RapidOCR Base64 Decoding | Fast CPU OCR (~50ms) to extract search keyword and sponsor domain | M3 | ORIGINAL_REQUEST §R3 |
| 7 | Sponsor PIN Extraction & checkPassword | Solve sponsor quest, extract 6-digit PIN, fill form, trigger `checkPassword` for final destination | M3 | ORIGINAL_REQUEST §R3 |
| 8 | E2E Integration & Verification | Validate end-to-end bypass on `https://link4m.net/go/68pw167Y` with CPU < 10% and solve time < 3s | M4 | ORIGINAL_REQUEST Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| 1 | M1: Pure Audio & Zero-Vision Standardization | Strip all vision AI methods from `recaptcha_solver.py`; standardize direct JS audio solver | None | COMPLETED |
| 2 | M2: Multi-Tier Resilient Solver Engine | Complete Tier 1 (Instant) + Tier 2 (Audio) + Tier 3 (2Captcha) fallback chain with token sync | M1 | COMPLETED |
| 3 | M3: SEO Traffic & Sponsor PIN Automation | Solidify RapidOCR Base64 decoding, sponsor anti-stall navigation, and `checkPassword` dispatch | None | COMPLETED |
| 4 | M4: E2E Integration & Performance Verification | End-to-end verification of `https://link4m.net/go/68pw167Y`, metrics benchmarking (CPU < 10%, solve < 3s) | M2, M3 | COMPLETED |

## Code Layout
- `src/core/recaptcha_solver.py`: 3-Tier reCAPTCHA v2 Solver without Vision AI.
- `src/core/twocaptcha_client.py`: 2Captcha Cloud API integration.
- `src/core/sponsor.py`: Sponsor domain extraction, RapidOCR decoding, widget PIN retrieval.
- `src/core/bypass.py`: Link4M bypass coordinator & `checkPassword` caller.
- `auto_bypass.py`: CLI runner.
- `tests/`: Test suite for individual tiers, OCR, and end-to-end flows.

## Interface Contracts
### `recaptcha_solver.py` ↔ `bypass.py`
- Function: `get_solver(headless: bool = True).solve_on_page(page: Page, timeout_sec: int = 40, container_selector: str = None) -> Dict[str, Any]`
- Return format:
  ```python
  {
      "success": True | False,
      "token": "03AFcWeA...",
      "type": "instant" | "audio_unblock_free" | "cloud_token",
      "time_ms": float,
      "error": Optional[str]
  }
  ```

### `sponsor.py` ↔ `bypass.py`
- Function: `detect_sponsor_domain(page_link: Page, campaign_payload: Optional[Dict]) -> Tuple[List[str], Optional[Dict]]`
- Function: `solve_sponsor_quest(context: BrowserContext, sponsor_candidates: List[str]) -> Tuple[Optional[str], Optional[str]]`
  - Returns: `(extracted_code: str, target_domain: str)`
