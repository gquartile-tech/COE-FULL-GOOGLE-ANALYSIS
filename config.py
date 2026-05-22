# config.py — Google CoE shared constants
# This file is the shared contract used by all 5 pillars.
# Do not modify STATUS values or ControlResult fields.
from __future__ import annotations

from dataclasses import dataclass

# ── Status constants (locked) ─────────────────────────────────────────────────
STATUS_OK      = "OK"
STATUS_FLAG    = "FLAG"
STATUS_PARTIAL = "PARTIAL"


# ── ControlResult (locked contract) ──────────────────────────────────────────
@dataclass(frozen=True)
class ControlResult:
    status: str
    what:   str = ""   # What We Saw — plain language, always includes real numbers
    why:    str = ""   # Why It Matters — one short action-oriented sentence
