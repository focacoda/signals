"""Confere que os ativos OTC vem da IQ, com velas reais.

Uso: python tools/check_otc.py
"""
from __future__ import annotations

import asyncio
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    with urllib.request.urlopen(
            "http://127.0.0.1:8000/api/assets", timeout=15) as r:
        import json
        assets = json.load(r)["assets"]

    otc = [a for a in assets if a["market"] == "otc"]
    print(f"ativos OTC no catalogo: {len(otc)}")
    fontes = {a["source"] for a in otc}
    print("fontes usadas:", fontes)
    if fontes != {"iq"}:
        print("ERRO: ainda ha fonte sintetica")
        return

    with urllib.request.urlopen(
            "http://127.0.0.1:8000/api/snapshot", timeout=20) as r:
        import json
        snap = json.load(r)
    print("erros do motor:", snap.get("errors") or "nenhum")
    print("avaliacoes ativas:", len(snap["assessments"]))


if __name__ == "__main__":
    main()
