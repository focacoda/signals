"""Confere o conector IQ nos tres timeframes operados.

Uso: python tools/check_timeframes.py [SIMBOLO]
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.feeds.base import Asset          # noqa: E402
from app.feeds.iq import IQFeed           # noqa: E402


async def main() -> None:
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "EURUSD").upper()
    feed = IQFeed()
    print("configured:", feed.configured)

    asset = Asset(symbol=symbol, name=symbol, market="forex",
                  source="iq", canonical=symbol)

    for tf in (60, 300, 900):
        started = time.time()
        candles = await feed.candles(asset, 60, tf)
        elapsed = time.time() - started
        gaps = (sorted({candles[i + 1].ts - candles[i].ts
                        for i in range(len(candles) - 1)})
                if len(candles) > 1 else [])
        print(f"tf={tf}s n={len(candles)} gaps={gaps} {elapsed:.1f}s")
        if candles:
            first, last = candles[0], candles[-1]
            print(f"   primeiro={first.ts} ultimo={last.ts} "
                  f"open={first.open:.6f} close={last.close:.6f}")

    print("status:", feed.status())
    print("price:", await feed.price(asset))
    await feed.close()


if __name__ == "__main__":
    asyncio.run(main())
