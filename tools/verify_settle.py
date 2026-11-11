"""Confere que os sinais OTC liquidaram com preco real da IQ."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DB_PATH  # noqa: E402


def main() -> None:
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row

    print("=== OTC liquidados recentemente ===")
    rows = c.execute("""
        SELECT id, symbol, expiry_min, direction, entry_price, exit_price,
               result, status
        FROM signals WHERE symbol LIKE '%_OTC'
        ORDER BY id DESC LIMIT 8
    """).fetchall()
    for r in rows:
        print(f"  #{r['id']:<4} {r['symbol']:<14} M{r['expiry_min']:<2} "
              f"{r['direction']:<4} {r['entry_price']:<12} -> "
              f"{r['exit_price']} {r['result']}")

    print()
    print("=== travados (vencidos e ainda 'open') ===")
    import time
    stuck = c.execute(
        "SELECT id, symbol, expires_at FROM signals "
        "WHERE status='open' AND expires_at < ?", (time.time() - 120,)
    ).fetchall()
    print(f"  {len(stuck)} sinal(is)")
    for r in stuck:
        print(f"   #{r['id']} {r['symbol']}")

    print()
    print("abertos por ativo:")
    for r in c.execute("""
        SELECT symbol, COUNT(*) n FROM signals
        WHERE status='open' GROUP BY symbol
    """):
        print(f"  {r['symbol']:<14} {r['n']}")


if __name__ == "__main__":
    main()
