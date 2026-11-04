"""Indicadores tecnicos em Python puro. Sem numpy: as series sao pequenas
(LOOKBACK ~120 pontos) e a clareza vale mais que micro-otimizacao aqui."""
from __future__ import annotations

from typing import Sequence


def ema(values: Sequence[float], period: int) -> float | None:
    """EMA classica. Retorna o ultimo valor, ou None se a serie for curta."""
    if len(values) < period:
        return None
    k = 2.0 / (period + 1.0)
    out = sum(values[:period]) / period
    for v in values[period:]:
        out = v * k + out * (1.0 - k)
    return out


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        gain = d if d > 0 else 0.0
        loss = -d if d < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(highs: Sequence[float], lows: Sequence[float],
        closes: Sequence[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    out = sum(trs[:period]) / period
    for tr in trs[period:]:
        out = (out * (period - 1) + tr) / period
    return out


def bollinger(values: Sequence[float], period: int = 20,
              mult: float = 2.0) -> tuple[float, float, float] | None:
    """Retorna (media, banda_inferior, banda_superior)."""
    if len(values) < period:
        return None
    window = list(values[-period:])
    mean = sum(window) / period
    var = sum((x - mean) ** 2 for x in window) / period
    sd = var ** 0.5
    return mean, mean - mult * sd, mean + mult * sd


def slope(values: Sequence[float], period: int = 10) -> float:
    """Inclinacao normalizada pelo preco medio, em % por barra."""
    if len(values) < period:
        return 0.0
    window = list(values[-period:])
    n = len(window)
    mean_x = (n - 1) / 2.0
    mean_y = sum(window) / n
    num = sum((i - mean_x) * (y - mean_y) for i, y in enumerate(window))
    den = sum((i - mean_x) ** 2 for i in range(n))
    if den == 0 or mean_y == 0:
        return 0.0
    return (num / den) / mean_y * 100.0


def stdev(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
