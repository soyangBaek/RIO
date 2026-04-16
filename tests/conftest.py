"""Test harness shared helpers.

Adds ``src/`` to ``sys.path`` so tests can simply ``from app.core ...``
without the caller having to configure PYTHONPATH. Kept minimal on purpose.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
