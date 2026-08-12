"""Unit handling.

RobotOM always reports in SI base units (m, N, N*m, Pa, rad) no matter what the
Robot user interface is set to display. Reporting those raw numbers as if they
were the on-screen units is the single easiest way to be wrong by a factor of
1000 while still looking plausible, so every result this server returns carries
an explicit `units` block and is converted through here.
"""

from __future__ import annotations

import os

# name -> divisor applied to the SI value
FORCE = {"N": 1.0, "kN": 1e3, "MN": 1e6}
MOMENT = {"Nm": 1.0, "kNm": 1e3, "MNm": 1e6}
LENGTH = {"m": 1.0, "cm": 1e-2, "mm": 1e-3}
DISPLACEMENT = {"m": 1.0, "cm": 1e-2, "mm": 1e-3}
STRESS = {"Pa": 1.0, "kPa": 1e3, "MPa": 1e6, "GPa": 1e9}

_DEFAULTS = {
    "force": "kN",
    "moment": "kNm",
    "length": "m",
    "displacement": "mm",
    "stress": "MPa",
}

_TABLES = {
    "force": FORCE,
    "moment": MOMENT,
    "length": LENGTH,
    "displacement": DISPLACEMENT,
    "stress": STRESS,
}

_current = dict(_DEFAULTS)
for _k in _current:
    _env = os.environ.get(f"ROBOT_MCP_UNIT_{_k.upper()}")
    if _env and _env in _TABLES[_k]:
        _current[_k] = _env


def current() -> dict[str, str]:
    return dict(_current)


def set_unit(kind: str, name: str) -> None:
    if kind not in _TABLES:
        raise ValueError(f"Unknown quantity '{kind}'. Use one of {sorted(_TABLES)}.")
    if name not in _TABLES[kind]:
        raise ValueError(f"Unknown {kind} unit '{name}'. Use one of {sorted(_TABLES[kind])}.")
    _current[kind] = name


def conv(kind: str, si_value: float | None, digits: int = 6) -> float | None:
    """SI value -> the configured output unit."""
    if si_value is None:
        return None
    try:
        return round(float(si_value) / _TABLES[kind][_current[kind]], digits)
    except (TypeError, ValueError):
        return None


def block(*kinds: str) -> dict[str, str]:
    """The `units` block to attach to a result payload."""
    out = {k: _current[k] for k in kinds}
    if "rotation" in kinds:
        out["rotation"] = "rad"
    return out
