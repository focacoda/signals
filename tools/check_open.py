"""Mostra os sinais abertos e detecta vencidos ainda presos."""
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
    now = time.time()

    rows = c.execute(
        "SELECT id, symbol, expiry_min, direction, expires_at "
        "FROM signals WHERE status='open' ORDER BY expires_at").fetchall()
    print(f"sinais abertos: {len(rows)}\n")
    for r in rows:
        left = r["expires_at"] - now
        flag = "  <-- VENCIDO" if left < -120 else ""
        print(f"  #{r['id']:<4} {r['symbol']:<14} M{r['expiry_min']:<2} "
              f"{r['direction']:<4} vence em {left:+.0f}s{flag}")

    print()
    per = c.execute(
        "SELECT symbol, COUNT(*) n FROM signals WHERE status='open' "
        "GROUP BY symbol HAVING n > 1").fetchall()
    if per:
        for r in per:
            print(f"  DUPLICADO: {r['symbol']} tem {r['n']}")
    else:
        print("  nenhum ativo com mais de 1 sinal aberto")


if __name__ == "__main__":
    main()
