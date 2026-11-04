"""Diagnostico: cada componente da estrategia isolado, sobre dados reais.

Proposito: descobrir se existe edge de verdade ou se o sinal e ruido. Roda
offline, sem servidor. Nao e teste automatizado -- e uma sonda.

Uso:  python -m tests.component_scan
"""
from __future__ import annotations

import asyncio
import statistics

from app.engine import indicators as ind
from app.engine.strategy import Candle
from app.feeds.binance import BinanceFeed
from app.feeds.base import Asset

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
BARS = 5000
PAYOUT = 85.0
BREAK_EVEN = 100.0 / (100.0 + PAYOUT) * 100.0   # 54.05%


def outcome(candles: list[Candle], i: int, direction: int, expiry: int):
    entry = candles[i].close
    exit_ = candles[i + expiry].close
    if abs(exit_ - entry) < 1e-12:
        return "tie"
    win = (exit_ > entry) == (direction == 1)
    return "win" if win else "loss"


def tally(rows: list[str]) -> tuple[int, int, int]:
    return (rows.count("win"), rows.count("loss"), rows.count("tie"))


def fmt(name: str, rows: list[str], exp: int) -> str:
    w, l, t = tally(rows)
    d = w + l
    rate = w / d * 100 if d else 0.0
    edge = rate - BREAK_EVEN
    flag = "  <-- acima do equilibrio" if edge > 1.0 else ""
    return (f"  {name:24} n={d:>5} taxa={rate:>6.2f}%  "
            f"edge={edge:>+6.2f}pp  empates={t:<4}{flag}")


class Series:
    def __init__(self, symbol: str, candles: list[Candle]) -> None:
        self.symbol = symbol
        self.candles = candles
        self.closes = [c.close for c in candles]

    def runs(self, expiry: int) -> dict[str, list[str]]:
        """Executa cada variante de sinal e devolve os resultados."""
        out: dict[str, list[str]] = {
            "trend_ema": [], "rsi": [], "bb_rev": [], "bb_break": [],
            "slope": [], "combinado_atual": [], "aleatorio": [],
        }
        closes = self.closes
        c = self.candles
        for i in range(60, len(c) - expiry):
            px = closes[i]
            if px <= 0:
                continue

            ef = ind.ema(closes[:i + 1], 9)
            es = ind.ema(closes[:i + 1], 21)
            if ef and es:
                gap = (ef - es) / px * 100
                if abs(gap) > 0.01:
                    out["trend_ema"].append(
                        outcome(c, i, 1 if gap > 0 else -1, expiry))

            r = ind.rsi(closes[:i + 1], 14)
            if r is not None and (r >= 62 or r <= 38):
                out["rsi"].append(outcome(c, i, 1 if r >= 62 else -1, expiry))

            bb = ind.bollinger(closes[:i + 1], 20, 2.0)
            if bb:
                mean, lo, hi = bb
                span = hi - lo
                if span > 0:
                    pos = (px - lo) / span
                    if pos < 0.08:
                        out["bb_rev"].append(outcome(c, i, 1, expiry))
                    elif pos > 0.92:
                        out["bb_rev"].append(outcome(c, i, -1, expiry))
                    # contrario: rompimento em vez de reversao
                    if pos < 0.08:
                        out["bb_break"].append(outcome(c, i, -1, expiry))
                    elif pos > 0.92:
                        out["bb_break"].append(outcome(c, i, 1, expiry))

            s = ind.slope(closes[:i + 1], 10)
            if abs(s) > 0.002:
                out["slope"].append(outcome(c, i, 1 if s > 0 else -1, expiry))

            # alterna direcao de forma deterministica para servir de baseline
            pseudo = (c[i].ts // 60) % 2
            out["aleatorio"].append(
                outcome(c, i, 1 if pseudo else -1, expiry))
        return out


async def main() -> None:
    feed = BinanceFeed()
    print(f"Payout {PAYOUT:.0f}% -> ponto de equilibrio {BREAK_EVEN:.2f}%")
    print(f"{BARS} barras de 1 min por ativo\n")

    for expiry in (1, 5, 15):
        print(f"=== expiracao {expiry} min ===")
        agg: dict[str, list[str]] = {}
        for sym in SYMBOLS:
            asset = Asset(symbol=sym, name=sym, market="crypto",
                          source="binance", canonical=sym)
            candles = await feed.candles(asset, BARS)
            if len(candles) < 200:
                print(f"  {sym}: sem dados")
                continue
            ser = Series(sym, candles)
            res = ser.runs(expiry)
            print(f" {sym} ({len(candles)} barras)")
            for name, rows in res.items():
                print(fmt(name, rows, expiry))
                agg.setdefault(name, []).extend(rows)
        print(f" AGREGADO dos {len(SYMBOLS)} ativos")
        for name, rows in agg.items():
            print(fmt(name, rows, expiry))
        print()

    await feed.close()


if __name__ == "__main__":
    asyncio.run(main())
