#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ RUNNER REGISTRY & ENGINE FACTORY FOR LINK4M BYPASS SUITE ⚡
Provides unified discovery and instantiation of BaseBypassRunner subclasses.
"""

from typing import Dict, Type, Optional
from base_runner import BaseBypassRunner, BypassResult

_RUNNERS: Dict[str, Type[BaseBypassRunner]] = {}

def register_runner(engine_key: str):
    """Decorator to register a runner implementation."""
    def decorator(cls: Type[BaseBypassRunner]):
        _RUNNERS[engine_key.upper()] = cls
        return cls
    return decorator

def get_runner(engine_key: str) -> Optional[BaseBypassRunner]:
    """Factory creating an instance of the appropriate runner."""
    cls = _RUNNERS.get(engine_key.upper())
    if cls:
        return cls()
    return None

def execute_engine(engine_key: str, target_url: str, headless: bool = True) -> BypassResult:
    """Dispatches bypass execution to the designated registered runner."""
    runner = get_runner(engine_key)
    if runner:
        return runner.run(target_url)

    # Fallback to direct script import if not registered
    return BypassResult(
        success=False,
        engine=engine_key,
        error_code="ERR_RUNNER_NOT_FOUND",
        error_message=f"No BaseBypassRunner registered for engine: {engine_key}"
    )
