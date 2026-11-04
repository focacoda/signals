"""Feed publico da Binance. Sem chave, sem cadastro, dados reais.

Por que ele existe no projeto: e a fonte que torna o track record auditavel.
Qualquer pessoa pode conferir o preco de fechamento em uma exchange publica
e refazer a conta do resultado. Os pares OTC nao tem essa propriedade.
"""
from __future__ import annotations

import time

import httpx

from ..engine.strategy import Candle
from .base import Asset

BASE = "https://api.binance.com/api/v3"


class BinanceFeed:
    name = "binance"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=10.0)
        self.available = True

    async def candles(self, asset: Asset, limit: int = 120) -> list[Candle]:
        try:
            r = await self._client.get(
                f"{BASE}/klines",
                params={"symbol": asset.canonical, "interval": "1m",
                        "limit": max(20, min(limit, 1000))},
            )
            if r.status_code != 200:
                self.available = False
                return []
            out: list[Candle] = []
            for row in r.json():
                out.append(Candle(
                    ts=int(row[0] / 1000),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                ))
            self.available = True
            return out
        except Exception:
            self.available = False
            return []

    async def price(self, asset: Asset) -> float | None:
        try:
            r = await self._client.get(
                f"{BASE}/ticker/price", params={"symbol": asset.canonical})
            if r.status_code != 200:
                return None
            return float(r.json()["price"])
        except Exception:
            return None

    async def close(self) -> None:
        await self._client.aclose()


def now_ms() -> int:
    return int(time.time() * 1000)
