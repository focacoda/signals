"""Mostra os sinais abertos que estao duplicados no mesmo ativo."""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DB_PATH  # noqa: E402


def main() -> None:
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row

    print("abertos:", c.execute(
        "SELECT COUNT(*) FROM signals WHERE status='open'").fetchone()[0])
    now = time.time()
    for r in c.execute("""
        SELECT symbol, COUNT(*) n FROM signals
        WHERE status='open' GROUP BY symbol HAVING n > 1
    """):
        print(f"\n{r['symbol']} — {r['n']} abertos")
        for s in c.execute("""
            SELECT id, expiry_min, direction, confidence, opened_at, expires_at
            FROM signals WHERE symbol=? AND status='open'
            ORDER BY opened_at
        """, (r["symbol"],)):
            print(f"   #{s['id']} M{s['expiry_min']:<2} {s['direction']:<4} "
                  f"conf={s['confidence']:<3} "
                  f"aberto ha {now - s['opened_at']:.0f}s "
                  f"vence em {s['expires_at'] - now:.0f}s")


if __name__ == "__main__":
    main()
