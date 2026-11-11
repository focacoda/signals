"""Normaliza resultados artificiais que entraram no banco por manutencao.

'skip_dup' e 'void' nao sao resultados de mercado: um veio de fechar
duplicata manualmente, o outro de anular sinal sem preco. Deixar os dois
como 'settled' polui o track record. Sao REMOVIDOS, nao convertidos.

    python tools/clean_results.py [--dry-run]
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

    rows = c.execute(
        "SELECT result, COUNT(*) n FROM signals "
        "WHERE result IN ('skip_dup','void') GROUP BY result").fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]}")

    if dry:
        print("\n[DRY-RUN] nada foi apagado")
        return

    n = c.execute(
        "DELETE FROM signals WHERE result IN ('skip_dup','void')").rowcount
    c.commit()
    print(f"\nremovidos: {n}")
    total = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    print(f"restantes no banco: {total}")


if __name__ == "__main__":
    main()
