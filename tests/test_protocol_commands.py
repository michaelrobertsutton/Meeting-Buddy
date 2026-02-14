from __future__ import annotations

import re
from pathlib import Path


def _docs_commands() -> set[str]:
    lines = Path("docs/protocol.md").read_text().splitlines()

    start = None
    end = None
    for i, line in enumerate(lines):
        if line.strip() == "## Commands (current)":
            start = i
        if start is not None and i > start and line.strip() == "## Events":
            end = i
            break

    assert start is not None and end is not None, "Could not locate Commands section in docs/protocol.md"

    section = "\n".join(lines[start:end])
    raw = re.findall(r"^- `([^`]+)`", section, flags=re.M)
    return {r.strip().split()[0] for r in raw}


def _backend_handler_commands() -> set[str]:
    src = Path("backend/server/websocket.py").read_text()

    # Grab handler map keys from the handlers = { ... } block.
    # We keep this intentionally simple and robust to formatting.
    m = re.search(r"handlers\s*=\s*\{(.*?)\}\s*\n\s*handler\s*=\s*handlers\.get\(cmd\)", src, flags=re.S)
    assert m, "Could not find handlers map in backend/server/websocket.py"

    block = m.group(1)
    keys = re.findall(r"\"([a-z0-9_]+)\"\s*:\s*self\._cmd_", block)
    return set(keys)


def test_protocol_docs_commands_exist_in_backend_handler_map() -> None:
    docs = _docs_commands()
    backend = _backend_handler_commands()

    missing = sorted(docs - backend)
    assert not missing, f"Commands documented but missing in backend handlers: {missing}"
