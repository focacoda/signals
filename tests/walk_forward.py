"""Validacao walk-forward do unico componente com edge aparente.

O `component_scan` mostrou que tendencia/RSI/inclinacao perdem para o
aleatorio, e que reversao nos extremos de Bollinger (bb_rev) fica acima.
+1pp pode ser sorte. Este script separa treino e teste e faz varredura de
parametros para responder: o edge sobrevive fora da amostra?

Uso: python -m tests.walk_forward
"""
from __future__ import annotations

import asyncio
from itertools import product

from app.engine import indicators as ind
from app.engine.strategy import Candle
from app.feeds.base import Asset
from app.feeds.binance import BinanceFeed

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
           "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
BARS = 5000
PAYOUT = 85.0
BREAK_EVEN = 100.0 / (100.0 + PAYOUT) * 100.0


def run_reversion(candles: list[Candle], period: int, mult: float,
                  thresh: float, expiry: int) -> list[str]:
    """Reversao: preco no extremo da banda -> aposta contra o movimento."""
    closes = [c.close for c in candles]
    rows: list[str] = []
    for i in range(period + 2, len(candles) - expiry):
        window = closes[:i + 1]
        bb = ind.bollinger(window, period, mult)
        if not bb:
            continue
        _, lo, hi = bb
        span = hi - lo
        if span <= 0:
            continue
        px = closes[i]
        pos = (px - lo) / span
        direction = 0
        if pos < thresh:
            direction = 1
        elif pos > 1 - thresh:
            direction = -1
        if not direction:
            continue
        entry, exit_ = closes[i], closes[i + expiry]
        if abs(exit_ - entry) < 1e-12:
            rows.append("tie")
        else:
            win = (exit_ > entry) == (direction == 1)
            rows.append("win" if win else "loss")
    return rows


def rate(rows: list[str]) -> tuple[float, int]:
    w, l = rows.count("win"), rows.count("loss")
    d = w + l
    return (w / d * 100 if d else 0.0), d


async def main() -> None:
    feed = BinanceFeed()
    print(f"Equilibrio para payout {PAYOUT:.0f}%: {BREAK_EVEN:.2f}%\n")

    data: dict[str, list[Candle]] = {}
    for s in SYMBOLS:
        a = Asset(symbol=s, name=s, market="crypto", source="binance",
                  canonical=s)
        c = await feed.candles(a, BARS)
        if len(c) > 500:
            data[s] = c
    await feed.close()
    print(f"Ativos carregados: {len(data)}\n")

    grid = list(product([15, 20, 30], [1.8, 2.0, 2.5], [0.10, 0.15],
                        [5, 15, 30]))
    results = []

    for period, mult, thresh, expiry in grid:
        train_rows, test_rows = [], []
        for s, candles in data.items():
            split = int(len(candles) * 0.6)
            tr = run_reversion(candles[:split], period, mult, thresh, expiry)
            te = run_reversion(candles[split:], period, mult, thresh, expiry)
            train_rows += tr
            test_rows += te
        tr_rate, tr_n = rate(train_rows)
        te_rate, te_n = rate(test_rows)
        if tr_n < 200 or te_n < 100:
            continue
        results.append({
            "period": period, "mult": mult, "thresh": thresh,
            "expiry": expiry, "train_rate": tr_rate, "train_n": tr_n,
            "test_rate": te_rate, "test_n": te_n,
            "test_edge": te_rate - BREAK_EVEN,
        })

    results.sort(key=lambda r: r["test_edge"], reverse=True)
    print(f"{'per':>4} {'mult':>5} {'thr':>5} {'exp':>4} "
          f"{'treino%':>8} {'n':>6} {'teste%':>8} {'n':>6} {'edge_te':>8}")
    for r in results[:15]:
        flag = "  <--" if r["test_edge"] > 1.0 else ""
        print(f"{r['period']:>4} {r['mult']:>5} {r['thresh']:>5} "
              f"{r['expiry']:>4} {r['train_rate']:>8.2f} {r['train_n']:>6} "
              f"{r['test_rate']:>8.2f} {r['test_n']:>6} "
              f"{r['test_edge']:>+8.2f}{flag}")

    print("\nPior metade (para ver o tamanho do ruido):")
    for r in results[-5:]:
        print(f"{r['period']:>4} {r['mult']:>5} {r['thresh']:>5} "
              f"{r['expiry']:>4} {r['train_rate']:>8.2f} {r['train_n']:>6} "
              f"{r['test_rate']:>8.2f} {r['test_n']:>6} "
              f"{r['test_edge']:>+8.2f}")

    pos = sum(1 for r in results if r["test_edge"] > 0)
    print(f"\n{r['test_n'] and pos}/{len(results)} combinacoes com edge "
          f"positivo fora da amostra ({pos/len(results)*100:.0f}%).")
    print("Se a taxa for proxima de 50%, o edge e indistinguivel de ruido.")


if __name__ == "__main__":
    asyncio.run(main())
