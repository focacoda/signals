"""Feed OTC sintetico, deterministico e reproduzivel.

Por que deterministico: o ponto do projeto e que o track record seja
conferivel. Mesmo um feed sintetico pode ser auditado se qualquer pessoa
reconstruir exatamente o mesmo preco a partir do simbolo e do minuto. A
funcao `price_at(symbol, minute)` e pura -- sem estado, sem aleatoriedade de
processo -- entao o resultado de um sinal pode ser recalculado meses depois.

Aviso que o dashboard expoe: estes precos sao gerados por nos, nao vem de
corretora. Servem para desenvolver e testar o motor, nao para operar.
"""
from __future__ import annotations

import math

from ..engine.strategy import Candle
from .base import Asset

BASE_PRICES = {
    "EURUSD_OTC": 1.0842, "GBPUSD_OTC": 1.2711, "USDJPY_OTC": 151.32,
    "AUDUSD_OTC": 0.6584, "USDCAD_OTC": 1.3625, "NZDUSD_OTC": 0.6013,
    "EURJPY_OTC": 164.05, "GBPJPY_OTC": 192.36, "EURCHF_OTC": 0.9412,
    "XAUUSD_OTC": 2334.10, "XAGUSD_OTC": 29.42,
}

# Volatilidade por minuto, em fracao do preco
VOLS = {
    "EURUSD_OTC": 0.00022, "GBPUSD_OTC": 0.00027, "USDJPY_OTC": 0.00024,
    "AUDUSD_OTC": 0.00026, "USDCAD_OTC": 0.00022, "NZDUSD_OTC": 0.00028,
    "EURJPY_OTC": 0.00029, "GBPJPY_OTC": 0.00034, "EURCHF_OTC": 0.00019,
    "XAUUSD_OTC": 0.00041, "XAGUSD_OTC": 0.00052,
}


def _hash01(*parts: object) -> float:
    """Hash estavel entre 0 e 1. Nao usa hash() do Python, que e salgado
    por processo e quebraria a reprodutibilidade entre execucoes."""
    h = 2166136261
    for p in parts:
        for b in str(p).encode("utf-8"):
            h ^= b
            h = (h * 16777619) & 0xFFFFFFFF
    return h / 0xFFFFFFFF


def _gauss(symbol: str, minute: int, salt: int = 0) -> float:
    """Aproximacao normal pela soma de 4 uniformes (Irwin-Hall)."""
    s = sum(_hash01(symbol, minute, salt, i) for i in range(4))
    return (s - 2.0) * 1.732


def _drift_minutes(symbol: str, minute: int) -> float:
    """Regime lento: ciclos de ~3h e ~9h. Cria tendencias que dao o que
    o motor analisar, em vez de ruido branco puro."""
    phase = _hash01(symbol, "phase") * math.tau
    a = math.sin(minute / 180.0 * math.tau + phase) * 0.35
    b = math.sin(minute / 540.0 * math.tau + phase * 1.7) * 0.65
    return (a + b) * 0.00013


def price_at(symbol: str, minute: int) -> float:
    """Preco de fechamento no minuto absoluto `minute`. Funcao pura."""
    base = BASE_PRICES.get(symbol, 1.0)
    vol = VOLS.get(symbol, 0.00025)
    # caminhada acumulada com memoria limitada: soma das ultimas 2400
    # contribuicoes evita O(n) por chamada mantendo determinismo
    lo = max(0, minute - 2400)
    total = 0.0
    for m in range(lo, minute + 1):
        total += _gauss(symbol, m) * vol + _drift_minutes(symbol, m)
    # decaimento do passado distante para manter o preco numa faixa
    decay = math.exp(-(minute - lo) / 6000.0) if minute > lo else 1.0
    return base * math.exp(total * 0.55 * decay)


def candle_at(symbol: str, minute: int) -> Candle:
    close = price_at(symbol, minute)
    prev = price_at(symbol, minute - 1)
    vol = VOLS.get(symbol, 0.00025)
    wick = abs(_gauss(symbol, minute, 7)) * vol * 0.6
    high = max(close, prev) * (1 + wick)
    low = min(close, prev) * (1 - wick)
    return Candle(ts=minute * 60, open=prev, high=high, low=low, close=close)


class OTCSimFeed:
    name = "sim_otc"

    def __init__(self) -> None:
        self.available = True

    async def candles(self, asset: Asset, limit: int = 120) -> list[Candle]:
        import time
        minute = int(time.time() // 60)
        return [candle_at(asset.canonical, m)
                for m in range(minute - limit + 1, minute + 1)]

    async def price(self, asset: Asset) -> float | None:
        import time
        return price_at(asset.canonical, int(time.time() // 60))

    async def close(self) -> None:
        return None
