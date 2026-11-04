"""Relatorio de analise no terminal, sem depender do navegador.

Uso:
    python -m tools.relatorio                  resumo geral
    python -m tools.relatorio --ativo BTCUSD   detalhe de um ativo
    python -m tools.relatorio --sinais 40      ultimos N sinais
    python -m tools.relatorio --por-hora       desempenho por hora do dia

Le o mesmo banco que o dashboard usa. Nao inventa nada: se nao houver
resultado suficiente, diz isso em vez de mostrar taxa bonita.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DB_PATH  # noqa: E402

LARGURA = 74


def linha(ch: str = "-") -> str:
    return ch * LARGURA


def titulo(txt: str) -> None:
    print()
    print(linha("="))
    print(f" {txt}")
    print(linha("="))


def conectar() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"\nBanco nao encontrado em {DB_PATH}")
        print("Rode 'iniciar.bat' primeiro para gerar sinais.\n")
        sys.exit(1)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def resumo(c: sqlite3.Connection) -> None:
    titulo("RESUMO GERAL")

    total = c.execute("SELECT COUNT(*) n FROM signals").fetchone()["n"]
    if not total:
        print("\nNenhum sinal gravado ainda. Inicie o servidor e aguarde.\n")
        return

    por_status = {r["status"]: r["n"] for r in c.execute(
        "SELECT status, COUNT(*) n FROM signals GROUP BY status")}
    por_result = {r["result"]: r["n"] for r in c.execute(
        "SELECT result, COUNT(*) n FROM signals WHERE result IS NOT NULL "
        "GROUP BY result")}

    w = por_result.get("win", 0)
    l = por_result.get("loss", 0)
    t = por_result.get("tie", 0)
    decidido = w + l
    taxa = w / decidido * 100 if decidido else 0.0

    print(f"\n  Sinais gravados ............ {total}")
    print(f"  Em aberto .................. {por_status.get('open', 0)}")
    print(f"  Liquidados ................. {por_status.get('settled', 0)}")
    print(f"  Ganhos / Perdas / Empates .. {w} / {l} / {t}")

    if decidido:
        print(f"\n  TAXA DE ACERTO REAL ........ {taxa:.2f}%")
        print(f"  Equilibrio (payout 85%) .... 54.05%")
        edge = taxa - 54.05
        sinal = "ACIMA do equilibrio" if edge > 0 else "ABAIXO do equilibrio"
        print(f"  Diferenca .................. {edge:+.2f} p.p.  ({sinal})")
        if decidido < 100:
            print(f"\n  ATENCAO: base de apenas {decidido} operacoes decididas.")
            print("  Abaixo de ~100 o numero ainda e ruido, nao estatistica.")
    else:
        print("\n  Ainda sem resultado decidido. Aguarde os vencimentos.\n")

    print(f"\n{linha()}")
    print("  POR MERCADO")
    print(linha())
    print(f"  {'mercado':<10} {'W':>5} {'L':>5} {'E':>4} {'taxa':>8}  {'auditavel':<10}")
    for r in c.execute(
            "SELECT market, "
            "SUM(result='win') w, SUM(result='loss') l, SUM(result='tie') t "
            "FROM signals WHERE result IS NOT NULL GROUP BY market"):
        d = (r["w"] or 0) + (r["l"] or 0)
        tx = (r["w"] or 0) / d * 100 if d else 0
        audit = "sim" if r["market"] == "crypto" else "nao"
        print(f"  {r['market']:<10} {r['w'] or 0:>5} {r['l'] or 0:>5} "
              f"{r['t'] or 0:>4} {tx:>7.2f}%  {audit:<10}")

    print(f"\n{linha()}")
    print("  POR ATIVO (somente os liquidados)")
    print(linha())
    print(f"  {'ativo':<14} {'W':>4} {'L':>4} {'E':>3} {'taxa':>8} {'fonte':<10}")
    for r in c.execute(
            "SELECT symbol, source, "
            "SUM(result='win') w, SUM(result='loss') l, SUM(result='tie') t "
            "FROM signals WHERE result IS NOT NULL "
            "GROUP BY symbol ORDER BY w+l DESC"):
        d = (r["w"] or 0) + (r["l"] or 0)
        tx = (r["w"] or 0) / d * 100 if d else 0
        print(f"  {r['symbol']:<14} {r['w'] or 0:>4} {r['l'] or 0:>4} "
              f"{r['t'] or 0:>3} {tx:>7.2f}% {r['source']:<10}")
    print()


def detalhe(c: sqlite3.Connection, ativo: str) -> None:
    titulo(f"ATIVO {ativo.upper()}")
    rows = c.execute(
        "SELECT * FROM signals WHERE symbol=? ORDER BY opened_at DESC LIMIT 30",
        (ativo.upper(),)).fetchall()
    if not rows:
        print(f"\n  Nenhum sinal para {ativo.upper()}.\n")
        return
    print(f"\n  {'#':>5} {'hora':<17} {'dir':<5} {'exp':>4} "
          f"{'conf':>5} {'entrada':>14} {'saida':>14} {'res':<6}")
    for r in rows:
        import datetime as dt
        hora = dt.datetime.fromtimestamp(r["opened_at"]).strftime("%d/%m %H:%M:%S")
        saida = f"{r['exit_price']:.6f}" if r["exit_price"] else "-"
        print(f"  {r['id']:>5} {hora:<17} {r['direction']:<5} "
              f"{r['expiry_min']:>4} {r['confidence']:>5} "
              f"{r['entry_price']:>14.6f} {saida:>14} "
              f"{r['result'] or 'aberto':<6}")
    print()


def sinais(c: sqlite3.Connection, n: int) -> None:
    titulo(f"ULTIMOS {n} SINAIS")
    rows = c.execute(
        "SELECT * FROM signals ORDER BY opened_at DESC LIMIT ?", (n,)).fetchall()
    if not rows:
        print("\n  Nenhum sinal gravado.\n")
        return
    print(f"\n  {'#':>5} {'ativo':<14} {'dir':<5} {'conf':>5} "
          f"{'res':<7} {'audit':<6}")
    for r in rows:
        print(f"  {r['id']:>5} {r['symbol']:<14} {r['direction']:<5} "
              f"{r['confidence']:>5} {r['result'] or 'aberto':<7} "
              f"{'sim' if r['verified'] else 'nao':<6}")
    print()


def por_hora(c: sqlite3.Connection) -> None:
    titulo("DESEMPENHO POR HORA DO DIA (UTC)")
    rows = c.execute(
        "SELECT CAST(strftime('%H', opened_at, 'unixepoch') AS INTEGER) h, "
        "SUM(result='win') w, SUM(result='loss') l "
        "FROM signals WHERE result IN ('win','loss') GROUP BY h ORDER BY h"
    ).fetchall()
    if not rows:
        print("\n  Sem resultados liquidados ainda.\n")
        return
    print(f"\n  {'hora':>5} {'W':>5} {'L':>5} {'taxa':>8}  grafico")
    for r in rows:
        d = r["w"] + r["l"]
        tx = r["w"] / d * 100 if d else 0
        barra = "#" * int(tx / 3)
        print(f"  {r['h']:>4}h {r['w']:>5} {r['l']:>5} {tx:>7.1f}%  {barra}")
    print("\n  Base pequena por hora: leia como pista, nao como conclusao.\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Relatorio do DevHub Signals")
    p.add_argument("--ativo", help="detalhar um ativo")
    p.add_argument("--sinais", type=int, help="listar N sinais recentes")
    p.add_argument("--por-hora", action="store_true",
                   help="desempenho por hora do dia")
    a = p.parse_args()

    c = conectar()
    if a.ativo:
        detalhe(c, a.ativo)
    elif a.sinais:
        sinais(c, a.sinais)
    elif a.por_hora:
        por_hora(c)
    else:
        resumo(c)


if __name__ == "__main__":
    main()
