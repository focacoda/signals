"""Persistencia em SQLite.

Regra de ouro do projeto: um sinal e gravado ANTES de o resultado existir.
Nao ha caminho de codigo que escreva um resultado sem que a linha do sinal ja
esteja no banco com data de emissao anterior ao vencimento. E isso que faz o
track record valer alguma coisa.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from .config import DB_PATH

_local = threading.local()
_write_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL,
    market        TEXT NOT NULL,
    source        TEXT NOT NULL,
    verified      INTEGER NOT NULL,
    strategy      TEXT NOT NULL,
    direction     TEXT NOT NULL,
    expiry_min    INTEGER NOT NULL,
    entry_price   REAL NOT NULL,
    confidence    INTEGER NOT NULL,
    score         REAL NOT NULL,
    reasons       TEXT NOT NULL,
    metrics       TEXT NOT NULL,
    opened_at     REAL NOT NULL,
    expires_at    REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'open',
    result        TEXT,
    exit_price    REAL,
    settled_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_signals_opened ON signals(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
"""


def _conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        _local.conn = c
    return c


def init() -> None:
    _conn()


def insert_signal(row: dict[str, Any]) -> int:
    sql = """INSERT INTO signals
        (symbol, market, source, verified, strategy, direction, expiry_min,
         entry_price, confidence, score, reasons, metrics, opened_at,
         expires_at, status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open')"""
    with _write_lock:
        c = _conn()
        cur = c.execute(sql, (
            row["symbol"], row["market"], row["source"], int(row["verified"]),
            row["strategy"], row["direction"], row["expiry_min"],
            row["entry_price"], row["confidence"], row["score"],
            json.dumps(row["reasons"]), json.dumps(row["metrics"]),
            row["opened_at"], row["expires_at"]))
        c.commit()
        return int(cur.lastrowid)


def pending_settlement(now: float) -> list[sqlite3.Row]:
    c = _conn()
    return c.execute(
        "SELECT * FROM signals WHERE status='open' AND expires_at <= ? "
        "ORDER BY expires_at", (now,)).fetchall()


def settle(signal_id: int, result: str, exit_price: float,
           settled_at: float) -> None:
    with _write_lock:
        c = _conn()
        c.execute(
            "UPDATE signals SET status='settled', result=?, exit_price=?, "
            "settled_at=? WHERE id=?",
            (result, exit_price, settled_at, signal_id))
        c.commit()


def row_to_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["reasons"] = json.loads(d["reasons"])
    d["metrics"] = json.loads(d["metrics"])
    d["verified"] = bool(d["verified"])
    d["expiry_min"] = int(d["expiry_min"])
    d["confidence"] = int(d["confidence"])
    return d


def recent(limit: int = 50) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM signals ORDER BY opened_at DESC LIMIT ?",
        (limit,)).fetchall()
    return [row_to_dict(r) for r in rows]


def open_signals() -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM signals WHERE status='open' ORDER BY opened_at DESC"
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def by_symbol(symbol: str, limit: int = 60) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM signals WHERE symbol=? ORDER BY opened_at DESC LIMIT ?",
        (symbol, limit)).fetchall()
    return [row_to_dict(r) for r in rows]


def count(symbol: str | None = None) -> int:
    c = _conn()
    if symbol:
        return int(c.execute(
            "SELECT COUNT(*) n FROM signals WHERE symbol=?",
            (symbol,)).fetchone()["n"])
    return int(c.execute("SELECT COUNT(*) n FROM signals").fetchone()["n"])


def open_signals_count() -> int:
    """Quantos sinais estao abertos agora. Usa o banco como fonte da verdade."""
    c = _conn()
    row = c.execute(
        "SELECT COUNT(*) n FROM signals WHERE status='open'"
    ).fetchone()
    return row["n"] if row else 0


def has_open_signal(symbol: str, expiry_min: int | None = None) -> bool:
    """Ha sinal aberto para o ativo.

    Com `expiry_min`, a pergunta e por prazo: um M15 em aberto nao impede
    um M5, porque sao operacoes distintas no mesmo ativo. Sem ele, olha
    qualquer prazo.
    """
    c = _conn()
    if expiry_min is None:
        row = c.execute(
            "SELECT COUNT(*) n FROM signals WHERE symbol=? AND status='open'",
            (symbol,)).fetchone()
    else:
        row = c.execute(
            "SELECT COUNT(*) n FROM signals WHERE symbol=? AND status='open' "
            "AND expiry_min=?", (symbol, int(expiry_min))).fetchone()
    return row["n"] > 0 if row else False


def stats(symbol: str | None = None, market: str | None = None,
          expiry_min: int | None = None,
          expiries: list[int] | None = None) -> dict:
    """Estatisticas calculadas a partir de tudo que foi registrado.

    Nao ha filtro de "melhores operacoes": perdas entram obrigatoriamente.
    Tie (empate no preco de vencimento) e contabilizado separado e nao entra
    no denominador da taxa de acerto, que e a mesma convencao que o mercado
    usa -- mas o numero de empates sempre e exibido junto.

    `expiries` restringe a prazos operados. Serve para o track record nao
    ser dominado por prazos que o motor nao emite mais -- hoje o historico
    de M1 (encerrado) e maior que o de M5 e M15 juntos, e somar tudo daria
    um numero que nao descreve o que esta sendo operado.
    """
    where = ["status='settled'"]
    args: list[Any] = []
    if symbol:
        where.append("symbol=?")
        args.append(symbol)
    if market:
        where.append("market=?")
        args.append(market)
    if expiry_min is not None:
        where.append("expiry_min=?")
        args.append(int(expiry_min))
    elif expiries:
        where.append("expiry_min IN (%s)" % ",".join("?" * len(expiries)))
        args.extend(int(e) for e in expiries)
    clause = " AND ".join(where)

    c = _conn()
    rows = c.execute(
        f"SELECT result, COUNT(*) n FROM signals WHERE {clause} "
        f"GROUP BY result", args).fetchall()
    counts = {r["result"]: r["n"] for r in rows}

    wins = counts.get("win", 0)
    losses = counts.get("loss", 0)
    ties = counts.get("tie", 0)
    decided = wins + losses
    win_rate = round(wins / decided * 100, 2) if decided else 0.0

    total = c.execute(
        f"SELECT COUNT(*) n FROM signals WHERE {clause}", args).fetchone()["n"]

    open_where = [w for w in where if not w.startswith("status=")]
    open_where.append("status='open'")
    pending = c.execute(
        f"SELECT COUNT(*) n FROM signals WHERE {' AND '.join(open_where)}",
        args).fetchone()["n"]

    by_market = {}
    for r in c.execute(
            f"SELECT market, result, COUNT(*) n FROM signals WHERE {clause} "
            f"GROUP BY market, result", args).fetchall():
        m = by_market.setdefault(r["market"], {"win": 0, "loss": 0, "tie": 0})
        m[r["result"]] = r["n"]
    for m in by_market.values():
        d = m["win"] + m["loss"]
        m["decided"] = d
        m["win_rate"] = round(m["win"] / d * 100, 2) if d else 0.0

    # Quebra por prazo: cada vencimento tem sua propria taxa. Somar prazos
    # num numero so esconde justamente o que se quer julgar -- se um deles
    # esta pagando e o outro nao.
    by_expiry: dict[str, dict] = {}
    for r in c.execute(
            f"SELECT expiry_min, result, COUNT(*) n FROM signals "
            f"WHERE {clause} GROUP BY expiry_min, result",
            args).fetchall():
        key = str(r["expiry_min"])
        e = by_expiry.setdefault(
            key, {"win": 0, "loss": 0, "tie": 0})
        e[r["result"]] = r["n"]
    for e in by_expiry.values():
        d = e["win"] + e["loss"]
        e["decided"] = d
        e["settled"] = e["win"] + e["loss"] + e["tie"]
        e["win_rate"] = round(e["win"] / d * 100, 2) if d else 0.0

    return {
        "symbol": symbol,
        "market": market,
        "expiry_min": expiry_min,
        "settled": total,
        "open": pending,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "decided": decided,
        "win_rate": win_rate,
        "by_market": by_market,
        "by_expiry": by_expiry,
    }
