"""Resumo do estado do banco de sinais."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DB_PATH  # noqa: E402


def main() -> None:
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row

    total = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    print("total:", total)

    print("\npor status/resultado:")
    for r in c.execute(
            "SELECT status, result, COUNT(*) n FROM signals "
            "GROUP BY status, result ORDER BY n DESC"):
        print(f"  {r['status']:<8} {str(r['result']):<8} {r['n']}")

    print("\npor fonte:")
    for r in c.execute(
            "SELECT source, COUNT(*) n FROM signals GROUP BY source"):
        print(f"  {r['source']:<10} {r['n']}")

    print("\nabertos por ativo:")
    for r in c.execute(
            "SELECT symbol, COUNT(*) n FROM signals "
            "WHERE status='open' GROUP BY symbol HAVING n > 1"):
        print(f"  ATENCAO {r['symbol']} tem {r['n']}")


if __name__ == "__main__":
    main()
