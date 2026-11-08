"""Conector para a API da IQ Option.

DECLARACAO DE LIMITE, e e importante que fique clara:

A IQ Option nao publica API oficial. O que existe sao endpoints internos do
proprio site, que mudam sem aviso e cujo uso nao esta coberto por contrato de
API. Este modulo implementa a sessao websocket minima necessaria para obter
velas e precos da conta do usuario, e TUDO falha de forma suave: se o login
nao completar, ou se o protocolo mudar, o feed se marca indisponivel e o
sistema continua com as outras fontes, exibindo a fonte real no dashboard.

Sem IQ_EMAIL/IQ_PASSWORD no ambiente, o conector nem tenta conectar.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time

import httpx

from ..config import IQ_EMAIL, IQ_ENABLED, IQ_PASSWORD, IQ_SSID
from ..engine.strategy import Candle
from .base import Asset

log = logging.getLogger("iq")

WS_URL = "wss://ws.iqoption.com/echo/websocket"
LOGIN_URL = "https://auth.iqoption.com/api/v2/login"

# Ativos da IQ que mapeiam para os simbolos canonicos do sistema.
# active_id e o identificador interno usado pela plataforma.
ACTIVE_IDS = {
    "EURUSD": 1, "GBPUSD": 2, "USDJPY": 3, "USDCHF": 4, "USDCAD": 5,
    "AUDUSD": 6, "NZDUSD": 8, "EURJPY": 9, "GBPJPY": 10, "EURGBP": 7,
    "AUDJPY": 11, "EURCHF": 12, "GBPCHF": 14,
    "XAUUSD": 74, "XAGUSD": 77,
    "BTCUSD": 1000, "ETHUSD": 1001,
}


class IQFeed:
    name = "iq"

    def __init__(self) -> None:
        self.available = False
        self.configured = bool(
            IQ_ENABLED and ((IQ_EMAIL and IQ_PASSWORD) or IQ_SSID))
        self._client = httpx.AsyncClient(timeout=15.0)
        self._ws = None
        self._reader: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._last_error: str | None = None
        self._prices: dict[str, float] = {}

    # ---------- infraestrutura ----------

    async def _connect(self) -> bool:
        if not self.configured:
            self._last_error = ("Credenciais ausentes: defina IQ_SSID (recomendado) "
                                "ou IQ_EMAIL + IQ_PASSWORD.")
            return False
        try:
            token = IQ_SSID
            if not token:
                r = await self._client.post(
                    LOGIN_URL,
                    json={"identifier": IQ_EMAIL, "password": IQ_PASSWORD},
                )
                if r.status_code != 200:
                    self._last_error = f"Login recusado (HTTP {r.status_code})"
                    log.warning(self._last_error)
                    return False
                body = r.json()
                token = body.get("data", {}).get("token") or body.get("token")
            if not token:
                self._last_error = "Login sem token na resposta"
                return False

            import websockets
            ctx = ssl.create_default_context()
            self._ws = await websockets.connect(
                WS_URL, ssl=ctx, ping_interval=20, max_size=2 ** 22)

            await self._ws.send(json.dumps({
                "name": "authenticate", "msg": {"ssid": token}}))

            self._reader = asyncio.create_task(self._read_loop())
            deadline = time.time() + 15
            while time.time() < deadline:
                if self.available:
                    return True
                if self._ws is None:
                    return False
                await asyncio.sleep(0.25)
            self._last_error = "Timeout aguardando autenticacao"
            return False
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            log.warning("Falha ao conectar na IQ Option: %s", self._last_error)
            return False

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                name = msg.get("name", "")
                if name == "ssid":
                    if msg.get("msg"):
                        self.available = True
                        self._last_error = None
                        await self._subscribe_streams()
                elif name == "quotes":
                    data = msg.get("msg") or {}
                    sid = str(data.get("active_id"))
                    if "price" in data:
                        self._prices[sid] = float(data["price"])
                fut = self._pending.pop(name, None)
                if fut and not fut.done():
                    fut.set_result(msg)
        except Exception as exc:
            log.info("Conexao IQ encerrada: %s", exc)
        finally:
            self.available = False
            self._ws = None

    async def _subscribe_streams(self) -> None:
        for sym, aid in ACTIVE_IDS.items():
            try:
                await self._ws.send(json.dumps({
                    "name": "subscribeMessage",
                    "msg": {"name": "front", "params": {"routingFilters": {
                        "active_id": aid,
                        "instrument_type": "turbo-option",
                        "leader_id": aid}}},
                }))
            except Exception:
                pass

    async def _request(self, name: str, payload: dict,
                       timeout: float = 8.0) -> dict | None:
        if not self._ws or not self.available:
            return None
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[name] = fut
        try:
            await self._ws.send(json.dumps({"name": name, "msg": payload}))
            return await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            self._pending.pop(name, None)
            return None

    # ---------- API do feed ----------

    async def candles(self, asset: Asset, limit: int = 120) -> list[Candle]:
        async with self._lock:
            if not self.available and not await self._connect():
                return []
            aid = ACTIVE_IDS.get(asset.canonical)
            if aid is None:
                return []
            end = int(time.time())
            start = end - limit * 60
            resp = await self._request("candles", {
                "active_id": aid, "interval": 60,
                "from": start, "to": end, "count": limit})
        if not resp:
            return []
        msg = resp.get("msg") or {}
        rows = msg.get("candles") or msg.get("data") or []
        out: list[Candle] = []
        for row in rows:
            if isinstance(row, dict):
                out.append(Candle(
                    ts=int(row.get("from", row.get("at", 0))),
                    open=float(row["open"]),
                    high=float(row["max"]),
                    low=float(row["min"]),
                    close=float(row["close"]),
                ))
            elif isinstance(row, (list, tuple)) and len(row) >= 5:
                out.append(Candle(
                    ts=int(row[0]), open=float(row[1]),
                    close=float(row[2]), high=float(row[3]), low=float(row[4])))
        return out

    async def price(self, asset: Asset) -> float | None:
        aid = ACTIVE_IDS.get(asset.canonical)
        if aid is None:
            return None
        return self._prices.get(str(aid))

    def status(self) -> dict:
        return {
            "configured": self.configured,
            "available": self.available,
            "error": self._last_error,
        }

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        await self._client.aclose()
