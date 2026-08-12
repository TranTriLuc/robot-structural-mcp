"""COM plumbing for Autodesk Robot Structural Analysis.

Robot's automation API is single-threaded: it answers only on the thread that
initialised the COM apartment. The MCP runtime calls tools from whatever thread
it likes, so every Robot call is funnelled through one long-lived STA thread.
"""

from __future__ import annotations

import os
import queue
import threading
from typing import Any, Callable

import pythoncom
import win32com.client

PROGID = "Robot.Application"

# --- RobotOM enums, read off robotom.tlb (do not guess these) ---------------

I_OT_NODE = 0
I_OT_BAR = 1
I_OT_CASE = 2
I_OT_PANEL = 4

I_LT_NODE_SUPPORT = 0
I_LT_BAR_SECTION = 3
I_LT_BAR_RELEASE = 4
I_LT_BAR_MATERIAL = 8

CASE_NATURE = {
    0: "permanent",
    1: "live",
    2: "wind",
    3: "snow",
    4: "temperature",
    5: "accidental",
    6: "seismic",
}

CASE_TYPE = {0: "simple", 1: "combination", 2: "code_combination", 3: "moving"}

CALC_STATUS = {
    -1: "in_progress",
    0: "completed",
    1: "failed_verification",
    2: "failed_calculation",
    3: "cancelled_by_user",
    4: "failed_generation",
    5: "failed_no_entitlement",
}


class RobotUnavailable(RuntimeError):
    pass


class WriteBlocked(PermissionError):
    pass


class _Worker:
    """Runs every COM call on one long-lived STA thread."""

    def __init__(self) -> None:
        self._jobs: queue.Queue[tuple[Callable[[], Any], queue.Queue[Any]]] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="robot-com")
        self._thread.start()

    def _loop(self) -> None:
        pythoncom.CoInitialize()
        try:
            while True:
                fn, reply = self._jobs.get()
                try:
                    reply.put(("ok", fn()))
                except Exception as exc:
                    reply.put(("err", exc))
        finally:
            pythoncom.CoUninitialize()

    def call(self, fn: Callable[[], Any]) -> Any:
        reply: queue.Queue[Any] = queue.Queue()
        self._jobs.put((fn, reply))
        status, value = reply.get()
        if status == "err":
            raise value
        return value


worker = _Worker()


def app() -> Any:
    try:
        return win32com.client.GetActiveObject(PROGID)
    except Exception as exc:
        raise RobotUnavailable(
            "Cannot reach Robot Structural Analysis. Start Robot, open a model, "
            f"and try again. (COM error: {exc})"
        ) from exc


def project() -> Any:
    proj = app().Project
    if proj is None:
        raise RobotUnavailable("Robot is running but no project is open.")
    return proj


def structure() -> Any:
    return project().Structure


def require_write(action: str) -> None:
    """Model-mutating tools are refused unless the user opts in explicitly."""
    flag = os.environ.get("ROBOT_MCP_ALLOW_WRITE", "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        raise WriteBlocked(
            f"Refused to {action}: this server is read-only by default. "
            "Set ROBOT_MCP_ALLOW_WRITE=1 in the MCP server env to permit writes."
        )


def max_items() -> int:
    try:
        return max(1, int(os.environ.get("ROBOT_MCP_MAX_ITEMS", "200")))
    except ValueError:
        return 200


def collection_numbers(coll: Any) -> list[int]:
    """IRobotCollection -> list of object numbers."""
    out: list[int] = []
    for i in range(1, int(coll.Count) + 1):
        try:
            out.append(int(coll.Get(i).Number))
        except Exception:
            continue
    return out


def selection_numbers(obj_type: int, text: str) -> list[int]:
    """Expand a Robot selection string ('1 3 5to9', 'all') to object numbers."""
    sel = structure().Selections.Create(obj_type)
    sel.FromText(text)
    return [int(sel.Get(i)) for i in range(1, int(sel.Count) + 1)]


def resolve_numbers(obj_type: int, selection: str | None, server: Any) -> list[int]:
    """Either an explicit selection string, or every object of that type."""
    if selection:
        return selection_numbers(obj_type, selection)
    return collection_numbers(server.GetAll())
