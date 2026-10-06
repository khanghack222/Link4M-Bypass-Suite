#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_tier1_strip_vision.py
--------------------------------
Test Tier 1: Zero-Vision & Pure Audio Standardization Verification.
Requirement: ORIGINAL_REQUEST §R1 & TEST_INFRA.md §Feature 1.
Asserts that no ONNX, YOLO, CLIP, or Visual tile components exist in recaptcha_solver.py.
"""

import sys
import os
import inspect
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
CORE_DIR = os.path.join(ROOT_DIR, "src", "core")

sys.path.insert(0, CORE_DIR)
sys.path.insert(0, ROOT_DIR)

import recaptcha_solver


def check_no_legacy_vision_attributes():
    solver = recaptcha_solver.get_solver()

    forbidden_attrs = [
        "yolo_detector",
        "_yolo_detector",
        "clip_model",
        "_clip_model",
        "ask_clip_tiles",
        "ask_gemini_vision_tiles",
        "ask_local_onnx_tiles",
        "solve_image_challenge",
    ]

    for attr in forbidden_attrs:
        assert not hasattr(solver, attr), f"Forbidden legacy vision attribute '{attr}' found on RecaptchaSolver!"

    print("[PASS] No legacy vision attributes found on RecaptchaSolver.")


def check_source_code_has_no_vision_imports():
    solver_file = inspect.getfile(recaptcha_solver)
    with open(solver_file, "r", encoding="utf-8") as f:
        content = f.read()

    forbidden_strings = [
        "import torch",
        "import cv2",
        "import transformers",
        "import onnxruntime",
        "vision_ai_recaptcha_solver",
        "yolo12x.pt",
        "recaptcha_classification_57k.onnx",
        "ask_clip_tiles",
        "ask_gemini_vision_tiles",
        "ask_local_onnx_tiles",
        "solve_image_challenge",
    ]

    for s in forbidden_strings:
        assert s not in content, f"Forbidden legacy vision code string '{s}' detected in {solver_file}!"

    print("[PASS] recaptcha_solver.py source code contains zero vision imports or references.")


def check_solver_interface_and_instantiation():
    s1 = recaptcha_solver.get_solver()
    s2 = recaptcha_solver.get_solver_instance()
    assert s1 is s2, "Singleton get_solver instance should be reused."
    assert hasattr(s1, "solve_on_page"), "Solver must provide solve_on_page method."
    assert hasattr(s1, "transcribe_audio_url"), "Solver must provide transcribe_audio_url method."
    assert hasattr(s1, "_sync_tokens"), "Solver must provide _sync_tokens method."
    print("[PASS] Solver public interface is compliant with specification.")


class TestTier1StripVision(unittest.TestCase):
    def test_no_legacy_vision_attributes(self):
        check_no_legacy_vision_attributes()

    def test_source_code_has_no_vision_imports(self):
        check_source_code_has_no_vision_imports()

    def test_solver_interface_and_instantiation(self):
        check_solver_interface_and_instantiation()


if __name__ == "__main__":
    print("=== RUNNING TIER 1 ZERO-VISION STANDARDIZATION TESTS ===")
    check_no_legacy_vision_attributes()
    check_source_code_has_no_vision_imports()
    check_solver_interface_and_instantiation()
    print("=== TIER 1 TESTS PASSED (100%) ===")
