"""Verificacao final do estado da conexao IQ Option.

Roda: python -m tools.verify_iq
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.feeds.iq import IQFeed  # noqa: E402


async def main() -> None:
    f = IQFeed()
    print(f"configurado: {f.configured}")
    ok = await f._connect()
    print(f"conectado (auth): {ok}")
    print(f"erro: {f._last_error}")
    print(f"precos recebidos: {len(f._prices)}")
    if f._prices:
        amostra = list(f._prices.items())[:5]
        print(f"amostra: {amostra}")
    await f.close()


if __name__ == "__main__":
    asyncio.run(main())
