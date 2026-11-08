import asyncio, json, sys
sys.path.insert(0, '.')
import websockets
from app.config import IQ_SSID

WS = "wss://ws.iqoption.com/echo/websocket"

async def send(ws, name, msg):
    await ws.send(json.dumps({"name": name, "msg": msg, "request_id": "1"}))

async def main():
    async with websockets.connect(WS, open_timeout=20) as ws:
        await send(ws, "ssid", IQ_SSID)
        for _ in range(4):
            raw = await asyncio.wait_for(ws.recv(), 10)
            m = json.loads(raw)
            if m.get("name") == "profile":
                print("AUTH OK user_id:", m["msg"].get("user_id"))
                break

        variants = [
            ("A", {"instrument_type": "forex", "instrument_id": 1, "timeframe": 60, "version": 4, "leader_id": 0}),
            ("B", {"instrument_type": "forex", "instrument_id": 1, "timeframe": 60, "version": 3, "leader_id": 0, "routingFilters": {"instrument_type": "forex"}}),
            ("C", {"instrument_id": 1, "instrument_type": "forex", "timeframe": 60, "version": 2, "from": 0, "to": 0}),
            ("D", {"instrument_type": "forex", "instrument_id": 1, "timeframe": 60, "version": 4, "count": 60, "realtime": True, "leader_id": 0}),
        ]
        for tag, payload in variants:
            await send(ws, "subscribe", payload)
            try:
                raw = await asyncio.wait_for(ws.recv(), 6)
                m = json.loads(raw)
                nm = m.get("name")
                body = str(m.get("msg"))[:220]
                print(f"[{tag}] {nm}: {body}")
                if nm == "candles" or "candles" in body:
                    print(f"[{tag}] SUCESSO")
            except asyncio.TimeoutError:
                print(f"[{tag}] sem resposta em 6s")
            await send(ws, "unsubscribe", {"instrument_type": "forex", "instrument_id": 1, "timeframe": 60})

asyncio.run(main())
