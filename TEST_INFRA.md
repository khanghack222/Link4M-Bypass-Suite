# E2E Test Infra: Link4M Bypass Suite

## Test Philosophy
- Opaque-box, requirement-driven, zero reliance on vision AI.
- Validate:
  1. No ONNX/YOLO/CLIP processes or memory allocated during reCAPTCHA solve.
  2. Average solve time < 3s for Audio and Instant tiers.
  3. CPU consumption remains strictly below 10% during execution.
  4. End-to-end bypass of `https://link4m.net/go/68pw167Y` successfully extracts destination URL.

## Feature Inventory & Test Coverage
| # | Feature | Requirement | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---|---|:---:|:---:|:---:|:---:|
| 1 | Strip Vision AI | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 2 | Direct JS Audio Solve | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 3 | Instant Tick Trust Score | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 4 | Cloud 2Captcha Fallback | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 5 | Intercept Advertise Payload | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 6 | RapidOCR Base64 Extraction | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 7 | Sponsor PIN Retrieval | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 8 | Destination URL Unlock | Acceptance Criteria | 5 | 5 | ✓ | ✓ |

## Test Architecture
- Test runner: Python 3.11 (`C:\Users\XUAN\AppData\Local\Programs\Python\Python311\python.exe`)
- Test scripts located in `tests/`:
  - `tests/test_tier1_strip_vision.py`: Asserts no ONNX/YOLO/CLIP imports or models loaded in `recaptcha_solver.py`.
  - `tests/test_tier2_audio_direct.py`: Asserts Direct JS click, in-memory MP3 audio solve in < 2s.
  - `tests/test_tier3_hybrid_fallback.py`: Asserts 3-tier fallback behavior.
  - `tests/test_tier4_rapidocr_sponsor.py`: Asserts RapidOCR decodes Base64 images from `adv.json` in < 50ms.
  - `tests/test_tier5_e2e_link4m.py`: Live integration test against `https://link4m.net/go/68pw167Y`.
