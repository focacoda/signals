"""Conector IQ Option via iqoptionapi (fork lukefeix).

Login real por e-mail/senha, velas reais dos ativos.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

from ..config import IQ_EMAIL, IQ_ENABLED, IQ_PASSWORD
from .base import Candle, Feed

log = logging.getLogger("iq")

_VENDOR = Path(__file__).resolve().parents[2] / "vendor" / "iqoptionapi-master"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

ACTIVE_IDS = {
    "EURUSD": 1,
    "GBPUSD": 2,
    "USDJPY": 3,
    "AUDUSD": 4,
    "USDCAD": 7,
    "USDCHF": 8,
    "EURGBP": 9,
    "EURJPY": 10,
    "BTCUSD": 1927,
}

TIMEFRAME = 60


class IQFeed:
    name = "iq"

    def __init__(self) -> None:
        self.configured = bool(
            IQ_ENABLED and IQ_EMAIL and IQ_PASSWORD)
        self.available = False
        self._api = None
        self._last_error: str | None = None
        self._lock = asyncio.Lock()

    def _login(self) -> bool:
        from iqoptionapi.stable_api import IQ_Option
        api = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
        ok, reason = api.connect()
        if not ok:
            self._last_error = str(reason)
            return False
        self._api = api
        return True

    async def _connect(self) -> bool:
        if not self.configured:
            return False
        async with self._lock:
            if self.available:
                return True
            try:
                ok = await asyncio.to_thread(self._login)
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                return False
            self.available = ok
            if ok:
                self._last_error = None
            return ok

    async def close(self) -> None:
        api, self._api = self._api, None
        self.available = False
        if api is not None:
            try:
                await asyncio.to_thread(api.close)
            except Exception:
                pass

    async def candles(self, asset, limit: int = 120) -> list[Candle]:
        symbol = getattr(asset, "symbol", asset)
        if not await self._connect():
            return []
        if symbol not in ACTIVE_IDS:
            return []
        api = self._api
        try:
            raw = await asyncio.to_thread(
                api.get_candles, symbol, TIMEFRAME, limit, int(time.time()))
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            self.available = False
            self._api = None
            return []
        if not raw:
            return []
        out: list[Candle] = []
        for c in raw:
            try:
                out.append(Candle(
                    ts=int(c["from"]),
                    open=float(c["open"]),
                    high=float(c["max"]),
                    low=float(c["min"]),
                    close=float(c["close"]),
                ))
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
        out.sort(key=lambda k: k.ts)
        return out

    def status(self) -> dict:
        return {
            "configured": self.configured,
            "available": self.available,
            "error": self._last_error,
        }