"""Contrato comum dos feeds e o registro de ativos."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..engine.strategy import Candle


@dataclass(frozen=True)
class Asset:
    symbol: str          # nome canonico usado no sistema, ex "EURUSD"
    name: str            # rotulo de exibicao
    market: str          # "forex" | "crypto" | "otc"
    source: str          # "iq" | "binance" | "sim"
    canonical: str       # id na fonte, ex "EURUSD" ou "BTCUSDT"
    payout: int = 85     # payout % usado nas calculadoras (binarias)
    verified: bool = True  # resultado auditavel por terceiro?

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "source": self.source,
            "payout": self.payout,
            "verified": self.verified,
        }


class Feed(Protocol):
    name: str
    available: bool

    async def candles(self, asset: Asset, limit: int = 120) -> list[Candle]:
        ...

    async def price(self, asset: Asset) -> float | None:
        ...

    async def close(self) -> None:
        ...
