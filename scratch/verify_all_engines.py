import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_DIR = os.path.join(ROOT_DIR, "src", "core")
for p in [CORE_DIR, ROOT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import config
print("[1] config imported successfully")

import cv2
print(f"[2] OpenCV imported: {cv2.__version__}")

import onnxruntime as ort
print(f"[3] ONNXRuntime imported: {ort.__version__}")

import ultralytics
print(f"[4] Ultralytics imported: {ultralytics.__version__}")

from recaptcha_solver import get_solver
s = get_solver(headless=True)
print("[5] RecaptchaSolver initialized successfully")

import bbmkts_runner
print("[6] bbmkts_runner imported successfully")

import gtraffic_runner
print("[7] gtraffic_runner imported successfully")

import layma_runner
print("[8] layma_runner imported successfully")

import bypass
print("[9] bypass (Link4M) imported successfully")

import trafficvn_runner
print("[10] trafficvn_runner imported successfully")

print("\n>>> ALL 10 MODULES AND RUNNERS VERIFIED 100% HEALTHY! <<<")
