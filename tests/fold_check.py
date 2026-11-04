"""O teste decisivo: a mesma configuracao sobrevive em folds independentes?

O walk_forward deu 40% no treino e 66% no teste para a mesma configuracao.
Isso nao pode ser edge -- edge aparece nos dois. E regime. Este script
corta a serie em 4 folds cronologicos, forca amostras nao sobrepostas
(sem trades com barras em comum) e mostra a taxa fold a fold.
"""
from __future__ import annotations

import asyncio

from app.engine import indicators as ind
from app.engine.strategy import Candle
from app.feeds.base import Asset
from app.feeds.binance import BinanceFeed

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
           "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
BARS = 5000
PAYOUT = 85.0
BREAK_EVEN = 100.0 / (100.0 + PAYOUT) * 100.0


def non_overlapping(candles: list[Candle], period: int, mult: float,
                    thresh: float, expiry: int) -> list[str]:
    closes = [c.close for c in candles]
    rows: list[str] = []
    i = period + 2
    step = max(1, expiry)
    while i < len(candles) - expiry:
        bb = ind.bollinger(closes[:i + 1], period, mult)
        if bb:
            _, lo, hi = bb
            span = hi - lo
            if span > 0:
                pos = (closes[i] - lo) / span
                direction = 1 if pos < thresh else -1 if pos > 1 - thresh else 0
                if direction:
                    entry, exit_ = closes[i], closes[i + expiry]
                    if abs(exit_ - entry) < 1e-12:
                        rows.append("tie")
                    else:
                        win = (exit_ > entry) == (direction == 1)
                        rows.append("win" if win else "loss")
                    i += step
                    continue
        i += 1
    return rows


def rate(rows: list[str]) -> tuple[float, int]:
    w, l = rows.count("win"), rows.count("loss")
    d = w + l
    return (w / d * 100 if d else 0.0), d


async def main() -> None:
    feed = BinanceFeed()
    data = {}
    for s in SYMBOLS:
        a = Asset(symbol=s, name=s, market="crypto", source="binance",
                  canonical=s)
        c = await feed.candles(a, BARS)
        if len(c) > 500:
            data[s] = c
    await feed.close()

    configs = [
        (30, 2.5, 0.15, 30),
        (30, 2.0, 0.10, 30),
        (20, 2.0, 0.10, 30),
        (30, 2.0, 0.10, 15),
    ]
    print(f"Equilibrio: {BREAK_EVEN:.2f}%   folds: 4, amostras nao sobrepostas\n")

    for period, mult, thresh, expiry in configs:
        print(f"--- periodo={period} mult={mult} limiar={thresh} "
              f"expiracao={expiry}min ---")
        fold_rows: list[list[str]] = [[] for _ in range(4)]
        for s, candles in data.items():
            n = len(candles)
            for f in range(4):
                seg = candles[f * n // 4:(f + 1) * n // 4]
                if len(seg) > period + expiry + 10:
                    fold_rows[f] += non_overlapping(
                        seg, period, mult, thresh, expiry)
        rates = []
        for f, rows in enumerate(fold_rows):
            r, n = rate(rows)
            rates.append(r)
            bar = "#" * int(r / 4)
            print(f"  fold {f + 1}: {r:>6.2f}%  n={n:>4}  {bar}")
        above = sum(1 for x in rates if x > BREAK_EVEN)
        spread = max(rates) - min(rates)
        print(f"  -> folds acima do equilibrio: {above}/4   "
              f"amplitude: {spread:.1f}pp\n")


if __name__ == "__main__":
    asyncio.run(main())
