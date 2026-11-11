"""Investiga por que alguns sinais terminam como `void`."""
from __future__ import annotations

import sqlite3
import time

DB = "data/signals.db"


def main() -> None:
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT id, symbol, expiry_min, opened_at, expires_at, entry_price,"
        " result, settled_at FROM signals WHERE result='void'"
        " ORDER BY id DESC LIMIT 10"
    ).fetchall()
    now = time.time()
    print(f"voids: {len(rows)}")
    for r in rows:
        dur = (r["expires_at"] - r["opened_at"]) if r["expires_at"] else 0
        late = (r["settled_at"] - r["expires_at"]) if (r["settled_at"] and r["expires_at"]) else 0
        print(
            f"  #{r['id']} {r['symbol']} M{r['expiry_min']}"
            f" dur={dur:.0f}s atraso={late:.0f}s ent={r['entry_price']}"
        )
    c.close()


if __name__ == "__main__":
    main()
