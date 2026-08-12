"""Register (or update) this server in ~/.claude.json.

Deliberately done in Python rather than PowerShell: ConvertTo-Json/ConvertFrom-Json
round-trips a large, deeply nested config lossily, and this file holds unrelated
settings that must survive untouched.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

NAME = "robot"


def main() -> int:
    repo = Path(__file__).resolve().parent
    python = repo / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        print(f"Not found: {python}. Run 'uv sync' first.", file=sys.stderr)
        return 1

    config = Path(os.environ["USERPROFILE"]) / ".claude.json"
    data: dict = {}
    if config.exists():
        raw = config.read_text(encoding="utf-8")
        if raw.strip():
            data = json.loads(raw)
        backup = config.with_suffix(".json.bak-robot-mcp")
        backup.write_text(raw, encoding="utf-8")
        print(f"  backup -> {backup}")

    data.setdefault("mcpServers", {})[NAME] = {
        "type": "stdio",
        "command": str(python),
        "args": ["-m", "robot_mcp"],
        "env": {"ROBOT_MCP_MAX_ITEMS": "200"},
    }
    config.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  registered MCP server '{NAME}' in {config}")
    print(f"  servers now: {', '.join(sorted(data['mcpServers']))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
