"""Mantem no maximo 1 sinal aberto por ativo.

Fecha os excedentes mantendo o MAIS RECENTE de cada ativo. Uso unico de
manutencao: a regra de origem ja impede duplicata, isto limpa o passado.

    python tools/dedupe_open.py [--dry-run]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DB_PATH  # noqa: E402


def main() -> None:
    dry = "--dry-run" in sys.argv
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row

    groups = c.execute("""
        SELECT symbol, COUNT(*) n FROM signals
        WHERE status='open' GROUP BY symbol HAVING n > 1
        ORDER BY symbol
    """).fetchall()

    closed = 0
    for g in groups:
        rows = c.execute("""
            SELECT id, expiry_min FROM signals
            WHERE symbol=? AND status='open'
            ORDER BY opened_at DESC, id DESC
        """, (g["symbol"],)).fetchall()
        keep = rows[0]
        for dup in rows[1:]:
            print(f"  {g['symbol']:<14} fecha #{dup['id']} (M{dup['expiry_min']})"
                  f" — mantem #{keep['id']} (M{keep['expiry_min']})")
            if not dry:
                c.execute(
                    "UPDATE signals SET status='settled', result='void' "
                    "WHERE id=?", (dup["id"],))
            closed += 1

    if dry:
        print(f"\n[DRY-RUN] fecharia {closed} sinal(is)")
        return

    c.commit()
    left = c.execute(
        "SELECT COUNT(*) FROM signals WHERE status='open'").fetchone()[0]
    dups = c.execute("""
        SELECT COUNT(*) FROM (SELECT symbol FROM signals
        WHERE status='open' GROUP BY symbol HAVING COUNT(*) > 1)
    """).fetchone()[0]
    print(f"\nfechados: {closed} | abertos: {left} | ativos duplicados: {dups}")


if __name__ == "__main__":
    main()
