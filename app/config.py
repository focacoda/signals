"""Configuracao central. Tudo por variavel de ambiente, com defaults seguros."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "signals.db"


def _load_env(path: Path) -> None:
    """Le .env no formato CHAVE=valor, sem dependencia externa.

    Variaveis ja definidas no ambiente tem prioridade, para que producao
    possa sobrescrever o arquivo sem edita-lo.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env(BASE_DIR / ".env")

# --- IQ Option ---
# A API publica/privada da IQ Option nao tem documentacao oficial. O conector
# tenta autenticar; sem credenciais ou se a conexao falhar, ele cai para o
# feed publico e o dashboard mostra a fonte real usada em cada ativo.
IQ_EMAIL = os.getenv("IQ_EMAIL", "")
IQ_PASSWORD = os.getenv("IQ_PASSWORD", "")
# SSID: token de sessao do navegador ja logado. Quando presente, dispensa o
# login HTTP -- util quando auth.iqoption.com esta bloqueado na rede mas o
# websocket (ws.iqoption.com) continua acessivel.
IQ_ENABLED = os.getenv("IQ_ENABLED", "1") == "1"

# --- Motor ---
# Segundos entre avaliacoes de cada ativo
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "5"))
# Frames de M1 usados no calculo dos indicadores
LOOKBACK = int(os.getenv("LOOKBACK", "120"))
# Prazos operados, em minutos, e o timeframe (em segundos) analisado para
# cada um. O timeframe de analise E o do vencimento: um sinal de 5 minutos
# nasce de velas de 5 minutos ja fechadas, e projeta o proximo candle de 5
# minutos. Nao existe analisar M1 e apostar M15.
# M1 removido: muito ruido para a estrategia atual de confluencia.
# Quando uma estrategia especifica para M1 for implementada, basta
# adicionar 1: 60 aqui e nos mapas abaixo.
TIMEFRAMES = {
    5: 300,
    15: 900,
}

# Vencimentos operados, do menor para o maior
EXPIRIES = sorted(TIMEFRAMES)

# Piso de confianca por vencimento.
MIN_CONFIDENCE_BY_EXPIRY = {
    5: int(os.getenv("MIN_CONFIDENCE_M5", "80")),
    15: int(os.getenv("MIN_CONFIDENCE_M15", "80")),
}

# Compatibilidade: o dashboard desenha a regra de emissao a partir daqui,
# e cada par diz "para este vencimento, o piso e X". Ordem = prazo crescente,
# porque um mesmo ativo pode ter sinal valido em mais de um prazo.
CONFIDENCE_BANDS = [
    (MIN_CONFIDENCE_BY_EXPIRY[exp], exp) for exp in EXPIRIES
]

# Piso absoluto: nada abaixo disso vira sinal, em nenhum prazo.
MIN_CONFIDENCE = min(MIN_CONFIDENCE_BY_EXPIRY.values())

# Cooldown por (ativo, prazo), em segundos, para nao emitir em sequencia.
# So e usado como piso: o cooldown efetivo de cada prazo e pelo menos o
# proprio candle, para nunca sair dois sinais do mesmo candle.
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "180"))


def cooldown_for(expiry: int) -> int:
    """Cooldown efetivo de um prazo: no minimo a duracao do seu candle.

    Sem isso o M15 emitia a cada 3 minutos, ou seja, tres sinais dentro de
    um candle de 15 -- cada um com vencimento diferente do candle que o
    originou, o que quebra a leitura de ganho e perda.
    """
    return max(COOLDOWN_SECONDS, TIMEFRAMES.get(expiry, 60))

# Ciclo de vida de um sinal, em tres estagios dentro do candle. Todos os
# tempos sao contados para tras a partir do fechamento do candle atual.
#
#   1. MEDICAO  -- comeca no ultimo minuto do candle
#   2. ALERTA   -- se a confluencia se manteve ate os ultimos ALERT segundos,
#                  o ativo entra em alerta (aparece no dashboard)
#   3. ABERTURA -- o sinal NAO abre no alerta: abre na virada exata do
#                  candle, e fecha um candle inteiro depois.
#
# Exemplo em M5, candle aberto as 10:00:
#   10:04:00  comeca a medir a confluencia
#   10:04:40  confluencia se manteve -> ALERTA
#   10:05:00  sinal ABRE (entrada = fechamento deste candle)
#   10:10:00  sinal FECHA
MEASURE_WINDOW_SECONDS = int(os.getenv("MEASURE_WINDOW_SECONDS", "60"))
ALERT_WINDOW_SECONDS = int(os.getenv("ALERT_WINDOW_SECONDS", "20"))

# Quantos segundos depois da virada o motor ainda tenta abrir um alerta
# confirmado. Se a fonte nao entregar o candle de fechamento nesse prazo,
# o alerta e descartado -- sinal sem preco de entrada nao existe.
OPEN_GRACE_SECONDS = int(os.getenv("OPEN_GRACE_SECONDS", "90"))

# Compatibilidade com o dashboard antigo: a janela anunciada e a de alerta.
EMIT_WINDOW_BY_EXPIRY = {
    exp: ALERT_WINDOW_SECONDS for exp in TIMEFRAMES
}
EMIT_WINDOW_SECONDS = ALERT_WINDOW_SECONDS

# --- Rastreamento de resultados ---
# Folga apos o vencimento antes de consultar o preco final, em segundos
SETTLE_GRACE = int(os.getenv("SETTLE_GRACE", "10"))
