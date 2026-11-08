"""Descobre o que a conta logada enxerga: instrumentos e candles."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets

from app.config import IQ_SSID

WS = "wss://ws.iqoption.com/echo/websocket"


async def main() -> None:
    async with websockets.connect(WS, max_size=8_000_000) as ws:
        await ws.send(json.dumps({"name": "ssid", "msg": IQ_SSID}))
        seen = []
        for _ in range(200):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=6)
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            seen.append(msg)
            if msg.get("name") == "profile":
                break

        print("=== INSTRUMENTOS ===")
        await ws.send(json.dumps({"name": "get-instruments", "msg": {}}))

        got = None
        for _ in range(80):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=8)
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            if "instrument" in msg.get("name", ""):
                got = msg
                break

        if not got:
            print("sem resposta de instrumentos")
            print("nomes recebidos:", sorted({m.get("name") for m in seen}))
            return

        body = got.get("msg") or {}
        types = body.get("result") or body
        if isinstance(types, dict):
            for k, v in types.items():
                n = len(v) if hasattr(v, "__len__") else "?"
                print(f"  tipo {k}: {n} itens")
                if k == "binary" and isinstance(v, list):
                    for it in v[:25]:
                        print("   ", it.get("id"), it.get("ticker"), it.get("name"))
        else:
            print(str(types)[:500])


if __name__ == "__main__":
    asyncio.run(main())
