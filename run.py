"""Ponto de entrada que funciona de qualquer diretorio.

`python -m uvicorn app.main:app` so encontra o pacote `app` se o diretorio
atual for a raiz do projeto. Este script ajusta o sys.path e chama o
uvicorn direto, entao o preview e atalhos podem executa-lo de onde estiver.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")
