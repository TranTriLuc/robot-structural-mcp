"""MCP tools for Autodesk Robot Structural Analysis Professional.

Read-only by default: nothing here mutates the model unless
ROBOT_MCP_ALLOW_WRITE is set, and the few tools that can are marked.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from . import units
from .com import (
    CALC_STATUS,
    CASE_NATURE,
    CASE_TYPE,
    I_LT_BAR_MATERIAL,
    I_LT_BAR_RELEASE,
    I_LT_BAR_SECTION,
    I_LT_NODE_SUPPORT,
    I_OT_BAR,
    I_OT_NODE,
    I_OLXDDT_CARTESIAN,
    I_OT_PANEL,
    app,
    collection_numbers,
    max_items,
    project,
    require_write,
    resolve_numbers,
    selection_numbers,
    structure,
    worker,
)

server = MCPServer(
    name="robot-structural",
    version="0.1.0",
    instructions=(
        "Reads models and analysis results from Autodesk Robot Structural Analysis. "
        "Robot must be running with a model open. Selections accept Robot's native "
        "syntax ('1 3 5to9', 'all'). Every result carries an explicit units block — "
        "RobotOM reports SI internally regardless of what Robot's UI displays, so "
        "never assume the numbers match the on-screen units."
    ),
)


def _names(array: Any) -> list[str]:
    out: list[str] = []
    try:
        for i in range(1, int(array.Count) + 1):
            out.append(str(array.Get(i)))
    except Exception:
        pass
    return out


def _page(items: list[Any], limit: int | None, offset: int) -> tuple[list[Any], dict[str, Any]]:
    cap = max_items() if limit is None else min(limit, max_items())
    window = items[offset : offset + cap]
    return window, {
        "total": len(items),
        "offset": offset,
        "returned": len(window),
        "truncated": offset + len(window) < len(items),
    }


def _safe(obj: Any, attr: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return default


# --------------------------------------------------------------------------
# Connection and project
# --------------------------------------------------------------------------


@server.tool(
    description="Check the Robot connection and report the open model: name, path, "
    "object counts, and whether analysis results are currently available."
)
def robot_status() -> dict[str, Any]:
    def work() -> dict[str, Any]:
        a = app()
        proj = _safe(a, "Project")
        if proj is None:
            return {"connected": True, "version": _safe(a, "Version"), "project": None}
        st = proj.Structure
        results = _safe(st, "Results")
        return {
            "connected": True,
            "version": _safe(a, "Version"),
            "project_name": _safe(proj, "Name"),
            "project_path": _safe(proj, "FileName"),
            "project_type": _safe(proj, "Type"),
            "nodes": int(_safe(st.Nodes, "Count", 0) or 0),
            "bars": int(_safe(st.Bars, "Count", 0) or 0),
            "cases": int(_safe(st.Cases, "Count", 0) or 0),
            "results_available": bool(_safe(results, "Available", False)),
            "results_status": CALC_STATUS.get(
                int(_safe(results, "Status", 99) or 99), "unknown"
            ),
            "write_enabled": _write_enabled(),
            "output_units": units.current(),
        }

    return worker.call(work)


def _write_enabled() -> bool:
    try:
        require_write("probe")
        return True
    except Exception:
        return False


@server.tool(description="Report and change the units this server converts results into.")
def robot_units(kind: str | None = None, unit: str | None = None) -> dict[str, Any]:
    if kind and unit:
        units.set_unit(kind, unit)
    return {
        "output_units": units.current(),
        "note": "RobotOM reports SI internally (m, N, N*m, Pa, rad); these are the "
        "units this server converts to before returning values.",
    }


@server.tool(
    description="Save the open Robot model. WRITE — requires ROBOT_MCP_ALLOW_WRITE=1."
)
def robot_save() -> dict[str, Any]:
    require_write("save the model")

    def work() -> dict[str, Any]:
        proj = project()
        proj.Save()
        return {"saved": True, "path": _safe(proj, "FileName")}

    return worker.call(work)


@server.tool(
    description="Open a Robot model file (.rtd). WRITE — requires ROBOT_MCP_ALLOW_WRITE=1, "
    "because it replaces whatever is currently open and can discard unsaved work."
)
def robot_open_model(path: str) -> dict[str, Any]:
    require_write("open a different model")

    def work() -> dict[str, Any]:
        proj = app().Project
        proj.Open(path)
        return {"opened": path, "project_name": _safe(proj, "Name")}

    return worker.call(work)


# --------------------------------------------------------------------------
# Model geometry
# --------------------------------------------------------------------------


@server.tool(
    description="Overview of the model: object counts, bounding box, and the section "
    "and material labels actually in use. Start here before querying details."
)
def robot_model_summary() -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        nodes = collection_numbers(st.Nodes.GetAll())
        xs, ys, zs = [], [], []
        for n in nodes:
            node = st.Nodes.Get(n)
            xs.append(float(node.X))
            ys.append(float(node.Y))
            zs.append(float(node.Z))
        bbox = None
        if xs:
            bbox = {
                "min": [units.conv("length", min(xs)), units.conv("length", min(ys)),
                        units.conv("length", min(zs))],
                "max": [units.conv("length", max(xs)), units.conv("length", max(ys)),
                        units.conv("length", max(zs))],
            }
        return {
            "counts": {
                "nodes": len(nodes),
                "bars": int(_safe(st.Bars, "Count", 0) or 0),
                "cases": int(_safe(st.Cases, "Count", 0) or 0),
            },
            "bounding_box": bbox,
            "sections": _names(st.Labels.GetAvailableNames(I_LT_BAR_SECTION)),
            "materials": _names(st.Labels.GetAvailableNames(I_LT_BAR_MATERIAL)),
            "supports": _names(st.Labels.GetAvailableNames(I_LT_NODE_SUPPORT)),
            "units": units.block("length"),
        }

    return worker.call(work)


@server.tool(
    description="List nodes with coordinates. `selection` takes Robot syntax "
    "('1 3 5to9'); omit it for every node."
)
def robot_list_nodes(
    selection: str | None = None, limit: int | None = None, offset: int = 0
) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        numbers = resolve_numbers(I_OT_NODE, selection, st.Nodes)
        window, page = _page(numbers, limit, offset)
        items = []
        for n in window:
            node = st.Nodes.Get(n)
            items.append(
                {
                    "number": n,
                    "x": units.conv("length", node.X),
                    "y": units.conv("length", node.Y),
                    "z": units.conv("length", node.Z),
                }
            )
        return {**page, "units": units.block("length"), "nodes": items}

    return worker.call(work)


@server.tool(description="Full detail for one node, including its support label if any.")
def robot_get_node(number: int) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        node = structure().Nodes.Get(number)
        support = None
        try:
            if node.HasLabel(I_LT_NODE_SUPPORT):
                support = node.GetLabelName(I_LT_NODE_SUPPORT)
        except Exception:
            pass
        return {
            "number": number,
            "x": units.conv("length", node.X),
            "y": units.conv("length", node.Y),
            "z": units.conv("length", node.Z),
            "support": support,
            "units": units.block("length"),
        }

    return worker.call(work)


@server.tool(
    description="List bars with end nodes, length, section and material. Filter with a "
    "Robot selection string and/or by section or material label name."
)
def robot_list_bars(
    selection: str | None = None,
    section: str | None = None,
    material: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        numbers = resolve_numbers(I_OT_BAR, selection, st.Bars)
        rows = []
        for n in numbers:
            bar = st.Bars.Get(n)
            sec = _label(bar, I_LT_BAR_SECTION)
            mat = _label(bar, I_LT_BAR_MATERIAL)
            if section and sec != section:
                continue
            if material and mat != material:
                continue
            rows.append(
                {
                    "number": n,
                    "start_node": int(_safe(bar, "StartNode", 0) or 0),
                    "end_node": int(_safe(bar, "EndNode", 0) or 0),
                    "length": units.conv("length", _safe(bar, "Length")),
                    "section": sec,
                    "material": mat,
                }
            )
        window, page = _page(rows, limit, offset)
        return {**page, "units": units.block("length"), "bars": window}

    return worker.call(work)


def _label(obj: Any, label_type: int) -> str | None:
    try:
        if obj.HasLabel(label_type):
            return str(obj.GetLabelName(label_type))
    except Exception:
        pass
    try:
        return str(obj.GetLabelName(label_type))
    except Exception:
        return None


@server.tool(description="Full detail for one bar, including release label and orientation.")
def robot_get_bar(number: int) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        bar = structure().Bars.Get(number)
        return {
            "number": number,
            "start_node": int(_safe(bar, "StartNode", 0) or 0),
            "end_node": int(_safe(bar, "EndNode", 0) or 0),
            "length": units.conv("length", _safe(bar, "Length")),
            "gamma_angle_rad": _safe(bar, "Gamma"),
            "section": _label(bar, I_LT_BAR_SECTION),
            "material": _label(bar, I_LT_BAR_MATERIAL),
            "release": _label(bar, I_LT_BAR_RELEASE),
            "units": units.block("length"),
        }

    return worker.call(work)


@server.tool(description="List panels (surface objects) present in the model.")
def robot_list_panels(
    selection: str | None = None, limit: int | None = None, offset: int = 0
) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        numbers = selection_numbers(I_OT_PANEL, selection or "all")
        window, page = _page(numbers, limit, offset)
        return {**page, "panels": [{"number": n} for n in window]}

    return worker.call(work)


# --------------------------------------------------------------------------
# Labels: sections, materials, supports, releases
# --------------------------------------------------------------------------


@server.tool(description="List the bar section labels defined in the model.")
def robot_list_sections() -> dict[str, Any]:
    return worker.call(
        lambda: {"sections": _names(structure().Labels.GetAvailableNames(I_LT_BAR_SECTION))}
    )


@server.tool(description="List the material labels defined in the model.")
def robot_list_materials() -> dict[str, Any]:
    return worker.call(
        lambda: {"materials": _names(structure().Labels.GetAvailableNames(I_LT_BAR_MATERIAL))}
    )


@server.tool(description="List support labels, and which nodes carry each one.")
def robot_list_supports() -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        labels = _names(st.Labels.GetAvailableNames(I_LT_NODE_SUPPORT))
        by_label: dict[str, list[int]] = {name: [] for name in labels}
        for n in collection_numbers(st.Nodes.GetAll()):
            name = _label(st.Nodes.Get(n), I_LT_NODE_SUPPORT)
            if name:
                by_label.setdefault(name, []).append(n)
        return {
            "labels": labels,
            "supported_nodes": {k: v for k, v in by_label.items() if v},
        }

    return worker.call(work)


@server.tool(description="List bar release labels, and which bars carry each one.")
def robot_list_releases() -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        labels = _names(st.Labels.GetAvailableNames(I_LT_BAR_RELEASE))
        by_label: dict[str, list[int]] = {}
        for n in collection_numbers(st.Bars.GetAll()):
            name = _label(st.Bars.Get(n), I_LT_BAR_RELEASE)
            if name:
                by_label.setdefault(name, []).append(n)
        return {"labels": labels, "released_bars": by_label}

    return worker.call(work)


# --------------------------------------------------------------------------
# Load cases and combinations
# --------------------------------------------------------------------------


def _case_row(case: Any) -> dict[str, Any]:
    return {
        "number": int(_safe(case, "Number", 0) or 0),
        "name": _safe(case, "Name"),
        "nature": CASE_NATURE.get(int(_safe(case, "Nature", -1) or -1), "unknown"),
        "type": CASE_TYPE.get(int(_safe(case, "Type", -1) or -1), "unknown"),
        "analysis_type": _safe(case, "AnalizeType"),
    }


@server.tool(description="List every load case and combination defined in the model.")
def robot_list_load_cases(limit: int | None = None, offset: int = 0) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        coll = st.Cases.GetAll()
        rows = []
        for i in range(1, int(coll.Count) + 1):
            try:
                rows.append(_case_row(coll.Get(i)))
            except Exception:
                continue
        window, page = _page(rows, limit, offset)
        return {**page, "cases": window}

    return worker.call(work)


@server.tool(description="List only the combinations, with their component cases and factors.")
def robot_list_combinations(limit: int | None = None, offset: int = 0) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        coll = st.Cases.GetAll()
        rows = []
        for i in range(1, int(coll.Count) + 1):
            case = coll.Get(i)
            if int(_safe(case, "Type", -1) or -1) == 0:
                continue
            row = _case_row(case)
            components = []
            try:
                factors = case.CaseFactors
                for j in range(1, int(factors.Count) + 1):
                    f = factors.Get(j)
                    components.append(
                        {"case": int(f.CaseNumber), "factor": round(float(f.Factor), 6)}
                    )
            except Exception:
                pass
            row["components"] = components
            rows.append(row)
        window, page = _page(rows, limit, offset)
        return {**page, "combinations": window}

    return worker.call(work)


@server.tool(description="List the load records inside one simple load case.")
def robot_get_load_records(case_number: int, limit: int | None = None) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        case = structure().Cases.Get(case_number)
        records = _safe(case, "Records")
        if records is None:
            return {"case": case_number, "records": [], "note": "Not a simple load case."}
        rows = []
        for i in range(1, int(records.Count) + 1):
            rec = records.Get(i)
            values = {}
            for k in range(0, 12):
                try:
                    values[str(k)] = round(float(rec.GetValue(k)), 6)
                except Exception:
                    break
            rows.append(
                {
                    "index": i,
                    "type": _safe(rec, "Type"),
                    "objects": _safe(rec.Objects, "ToText") if _safe(rec, "Objects") else None,
                    "values_si": values,
                }
            )
        window, page = _page(rows, limit, 0)
        return {
            "case": case_number,
            **page,
            "records": window,
            "note": "values_si are raw RobotOM values (SI) — record layout depends on load type.",
        }

    return worker.call(work)


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------


@server.tool(description="Whether results are available, and the last calculation status.")
def robot_calculation_status() -> dict[str, Any]:
    def work() -> dict[str, Any]:
        results = structure().Results
        return {
            "results_available": bool(_safe(results, "Available", False)),
            "status": CALC_STATUS.get(int(_safe(results, "Status", 99) or 99), "unknown"),
        }

    return worker.call(work)


@server.tool(
    description="Run the analysis. Long-running and it overwrites existing results, so "
    "it refuses unless confirm=true. Robot's progress window is suppressed, otherwise "
    "the modal dialog would block automation."
)
def robot_run_calculation(confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise ValueError(
            "Refused: running the analysis overwrites existing results and can take a "
            "long time. Call again with confirm=true if that is intended."
        )

    def work() -> dict[str, Any]:
        engine = project().CalcEngine
        try:
            engine.UseStatusWindow = False
        except Exception:
            pass
        code = engine.Calculate()
        results = structure().Results
        return {
            "return_code": int(code) if code is not None else None,
            "status": CALC_STATUS.get(int(code) if code is not None else 99, "unknown"),
            "results_available": bool(_safe(results, "Available", False)),
        }

    return worker.call(work)


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

_FORCE_COMPONENTS = ("FX", "FY", "FZ")
_MOMENT_COMPONENTS = ("MX", "MY", "MZ")


def _force_row(data: Any) -> dict[str, Any]:
    row = {c: units.conv("force", _safe(data, c)) for c in _FORCE_COMPONENTS}
    row.update({c: units.conv("moment", _safe(data, c)) for c in _MOMENT_COMPONENTS})
    return row


@server.tool(
    description="Internal forces along bars. `positions` are relative (0.0 = start, "
    "1.0 = end); the default samples both ends and midspan. Returns FX/FY/FZ and "
    "MX/MY/MZ per bar per case per position."
)
def robot_get_bar_forces(
    bars: str,
    cases: str,
    positions: list[float] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        if not bool(_safe(st.Results, "Available", False)):
            raise RuntimeError(
                "No analysis results are available. Run the analysis first "
                "(robot_run_calculation) or open a model that has been calculated."
            )
        pts = positions or [0.0, 0.5, 1.0]
        bar_numbers = selection_numbers(I_OT_BAR, bars)
        case_numbers = selection_numbers(2, cases)  # I_OT_CASE
        server_ = st.Results.Bars.Forces
        rows: list[dict[str, Any]] = []
        cap = max_items() if limit is None else min(limit, max_items())
        truncated = False
        for b in bar_numbers:
            for c in case_numbers:
                for p in pts:
                    if len(rows) >= cap:
                        truncated = True
                        break
                    try:
                        data = server_.Value(b, c, float(p))
                    except Exception as exc:
                        rows.append({"bar": b, "case": c, "position": p, "error": str(exc)})
                        continue
                    rows.append({"bar": b, "case": c, "position": p, **_force_row(data)})
                if truncated:
                    break
            if truncated:
                break
        return {
            "returned": len(rows),
            "truncated": truncated,
            "units": units.block("force", "moment"),
            "forces": rows,
        }

    return worker.call(work)


@server.tool(
    description="Envelope of bar internal forces: min and max of each component across "
    "the requested bars, cases and positions, with where each extreme occurs. This is "
    "the input a member design check needs."
)
def robot_get_bar_extreme_forces(
    bars: str, cases: str, positions: list[float] | None = None
) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        if not bool(_safe(st.Results, "Available", False)):
            raise RuntimeError("No analysis results are available.")
        pts = positions or [0.0, 0.25, 0.5, 0.75, 1.0]
        bar_numbers = selection_numbers(I_OT_BAR, bars)
        case_numbers = selection_numbers(2, cases)
        server_ = st.Results.Bars.Forces
        comps = _FORCE_COMPONENTS + _MOMENT_COMPONENTS
        best: dict[str, dict[str, Any]] = {}
        samples = 0
        for b in bar_numbers:
            for c in case_numbers:
                for p in pts:
                    try:
                        data = server_.Value(b, c, float(p))
                    except Exception:
                        continue
                    samples += 1
                    row = _force_row(data)
                    for comp in comps:
                        v = row.get(comp)
                        if v is None:
                            continue
                        slot = best.setdefault(
                            comp,
                            {"min": None, "max": None, "min_at": None, "max_at": None},
                        )
                        where = {"bar": b, "case": c, "position": p}
                        if slot["min"] is None or v < slot["min"]:
                            slot["min"], slot["min_at"] = v, where
                        if slot["max"] is None or v > slot["max"]:
                            slot["max"], slot["max_at"] = v, where
        return {
            "bars_scanned": len(bar_numbers),
            "cases_scanned": len(case_numbers),
            "samples": samples,
            "units": units.block("force", "moment"),
            "envelope": best,
        }

    return worker.call(work)


@server.tool(description="Node displacements (UX/UY/UZ) and rotations (RX/RY/RZ) per case.")
def robot_get_node_displacements(
    nodes: str, cases: str, limit: int | None = None
) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        if not bool(_safe(st.Results, "Available", False)):
            raise RuntimeError("No analysis results are available.")
        node_numbers = selection_numbers(I_OT_NODE, nodes)
        case_numbers = selection_numbers(2, cases)
        server_ = st.Results.Nodes.Displacements
        rows: list[dict[str, Any]] = []
        cap = max_items() if limit is None else min(limit, max_items())
        for n in node_numbers:
            for c in case_numbers:
                if len(rows) >= cap:
                    break
                try:
                    d = server_.Value(n, c)
                except Exception as exc:
                    rows.append({"node": n, "case": c, "error": str(exc)})
                    continue
                rows.append(
                    {
                        "node": n,
                        "case": c,
                        "UX": units.conv("displacement", _safe(d, "UX")),
                        "UY": units.conv("displacement", _safe(d, "UY")),
                        "UZ": units.conv("displacement", _safe(d, "UZ")),
                        "RX": _safe(d, "RX"),
                        "RY": _safe(d, "RY"),
                        "RZ": _safe(d, "RZ"),
                    }
                )
        return {
            "returned": len(rows),
            "truncated": len(rows) >= cap,
            "units": units.block("displacement", "rotation"),
            "displacements": rows,
        }

    return worker.call(work)


@server.tool(
    description="Support reactions per node per case — the numbers a foundation design "
    "starts from."
)
def robot_get_node_reactions(
    nodes: str, cases: str, limit: int | None = None
) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        st = structure()
        if not bool(_safe(st.Results, "Available", False)):
            raise RuntimeError("No analysis results are available.")
        node_numbers = selection_numbers(I_OT_NODE, nodes)
        case_numbers = selection_numbers(2, cases)
        server_ = st.Results.Nodes.Reactions
        rows: list[dict[str, Any]] = []
        cap = max_items() if limit is None else min(limit, max_items())
        for n in node_numbers:
            for c in case_numbers:
                if len(rows) >= cap:
                    break
                try:
                    r = server_.Value(n, c)
                except Exception as exc:
                    rows.append({"node": n, "case": c, "error": str(exc)})
                    continue
                rows.append({"node": n, "case": c, **_force_row(r)})
        return {
            "returned": len(rows),
            "truncated": len(rows) >= cap,
            "units": units.block("force", "moment"),
            "reactions": rows,
        }

    return worker.call(work)


_SHELL_FORCES = ("NXX", "NYY", "NXY", "QXX", "QYY")
_SHELL_MOMENTS = ("MXX", "MYY", "MXY")
_X_DIRECTIONS = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def _fe_params() -> Any:
    import win32com.client

    return win32com.client.Dispatch("Robot.FeResultParams")


@server.tool(
    description="Shell forces of a panel at its nodes: NXX/NYY/NXY and QXX/QYY (force per "
    "metre) and MXX/MYY/MXY (moment per metre), per node per case. `x_direction` sets the "
    "x axis of the result frame: 'local' (default) is each finite element's own local "
    "system — what Robot's tables show, but it can differ from element to element and "
    "change when the mesh is regenerated, so MXX/MYY may come out swapped at some nodes; "
    "'x', 'y' or 'z' fixes the x axis along that global direction (projected on the panel), "
    "which gives mesh-independent results (e.g. 'x' for slabs, 'z' for walls). `nodes` "
    "defaults to all nodes of the panel."
)
def robot_get_panel_forces(
    panel: int,
    cases: str,
    nodes: str | None = None,
    x_direction: str = "local",
    limit: int | None = None,
) -> dict[str, Any]:
    if x_direction not in ("local", *_X_DIRECTIONS):
        raise ValueError("x_direction must be 'local', 'x', 'y' or 'z'.")

    def work() -> dict[str, Any]:
        st = structure()
        if not bool(_safe(st.Results, "Available", False)):
            raise RuntimeError("No analysis results are available.")
        obj = st.Objects.Get(int(panel))
        if obj is None:
            raise ValueError(f"Panel {panel} does not exist.")
        node_numbers = selection_numbers(I_OT_NODE, nodes or str(_safe(obj, "Nodes", "")))
        case_numbers = selection_numbers(2, cases)
        params = _fe_params()
        params.Panel = int(panel)
        if x_direction != "local":
            params.SetDirX(I_OLXDDT_CARTESIAN, *_X_DIRECTIONS[x_direction])
        fe = st.Results.FiniteElems
        rows: list[dict[str, Any]] = []
        cap = max_items() if limit is None else min(limit, max_items())
        for c in case_numbers:
            for n in node_numbers:
                if len(rows) >= cap:
                    break
                params.Node = n
                params.Case = c
                try:
                    r = fe.Detailed(params)
                except Exception as exc:
                    rows.append({"node": n, "case": c, "error": str(exc)})
                    continue
                row = {"node": n, "case": c}
                row.update({k: units.conv("force", _safe(r, k)) for k in _SHELL_FORCES})
                row.update({k: units.conv("moment", _safe(r, k)) for k in _SHELL_MOMENTS})
                rows.append(row)
        u = units.current()
        return {
            "panel": int(panel),
            "x_direction": x_direction,
            "returned": len(rows),
            "truncated": len(rows) >= cap,
            "units": {"force_per_length": f"{u['force']}/m", "moment_per_length": f"{u['moment']}/m"},
            "forces": rows,
        }

    return worker.call(work)


# --------------------------------------------------------------------------
# Introspection — used to grow the tool set against a live Robot session
# --------------------------------------------------------------------------


@server.tool(
    description="Read-only inspection of the RobotOM object graph. `path` is a dotted "
    "attribute path from a root of 'app', 'project', 'structure' or 'results' "
    "(e.g. 'results.Extremes'). Lists the members available on that object. Use this "
    "to discover API surface this server does not wrap yet."
)
def robot_inspect(path: str = "") -> dict[str, Any]:
    def work() -> dict[str, Any]:
        roots = {
            "app": app,
            "project": project,
            "structure": structure,
            "results": lambda: structure().Results,
        }
        parts = [p for p in path.split(".") if p]
        if not parts:
            return {"roots": sorted(roots)}
        if parts[0] not in roots:
            raise ValueError(f"Path must start with one of {sorted(roots)}.")
        obj = roots[parts[0]]()
        for p in parts[1:]:
            obj = getattr(obj, p)
        members = sorted(m for m in dir(obj) if not m.startswith("_"))
        scalars = {}
        for m in members:
            try:
                v = getattr(obj, m)
            except Exception:
                continue
            if isinstance(v, (int, float, str, bool)):
                scalars[m] = v
        return {"path": path, "type": str(type(obj)), "members": members, "scalar_values": scalars}

    return worker.call(work)


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
