"""Minimal WebSocket tail client for Meeting Buddy.

Useful while developing the native shell (Issue #83). Connects to the backend
and prints snapshot/update messages.

Usage:
  python examples/ws_tail.py

Requirements:
  pip install websockets

(We keep this script dependency-light; it does not require the full app deps.)
"""

import asyncio
import json

import websockets


async def main():
    url = "ws://localhost:8765"
    print(f"Connecting to {url} …")

    async with websockets.connect(url) as ws:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                print(raw)
                continue

            mtype = msg.get("type")
            if mtype in ("snapshot", "update"):
                aq = msg.get("active_question")
                pv = msg.get("protocol_version")
                ver = msg.get("version")
                print(f"[{mtype}] protocol={pv} version={ver} question={aq!r}")
            else:
                print(f"[{mtype}] {msg}")


if __name__ == "__main__":
    asyncio.run(main())
