"""Configuracao central. Tudo por variavel de ambiente, com defaults seguros."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "signals.db"

# --- IQ Option ---
# A API publica/privada da IQ Option nao tem documentacao oficial. O conector
# tenta autenticar; sem credenciais ou se a conexao falhar, ele cai para o
# feed publico e o dashboard mostra a fonte real usada em cada ativo.
IQ_EMAIL = os.getenv("IQ_EMAIL", "")
IQ_PASSWORD = os.getenv("IQ_PASSWORD", "")
IQ_ENABLED = os.getenv("IQ_ENABLED", "1") == "1"

# --- Motor ---
# Segundos entre avaliacoes de cada ativo
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "5"))
# Frames de M1 usados no calculo dos indicadores
LOOKBACK = int(os.getenv("LOOKBACK", "120"))
# Timeframes de expiracao suportados (minutos)
EXPIRIES = [1, 5, 15]

# Faixas de confianca por expiracao: (confianca minima, expiracao em minutos).
# A regra e "estritamente acima", entao 95.0 exato nao passa para M1.
# Prazo mais curto exige confianca maior porque 1 minuto e quase todo ruido:
# uma direcao fraca em M1 e moeda justa, nao sinal.
# Avaliado de cima para baixo -- a primeira faixa satisfeita define o prazo.
CONFIDENCE_BANDS = [
    (95, 1),   # >= 95% -> M1
    (80, 5),   # >= 80% -> M5
    (80, 15),  # >= 80% -> M15
]
# Piso absoluto: nada abaixo disso vira sinal
MIN_CONFIDENCE = int(os.getenv("MIN_CONFIDENCE", "80"))
# Cooldown por ativo, em segundos, para naoemitir sinal em sequencia
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "180"))

# --- Rastreamento de resultados ---
# Folga apos o vencimento antes de consultar o preco final, em segundos
SETTLE_GRACE = int(os.getenv("SETTLE_GRACE", "10"))
