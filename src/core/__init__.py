# -*- coding: utf-8 -*-
"""Package bootstrap: make flat core imports work from the repo root too."""

import os
import sys

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

# Same module object for ``runner_registry`` and ``src.core.runner_registry``.
try:
    from . import runner_registry as _runner_registry  # noqa: F401
    sys.modules.setdefault("runner_registry", _runner_registry)
except Exception:  # pragma: no cover - optional browser deps on bare boxes
    pass
