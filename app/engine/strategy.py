"""Estrategia de confluencia.

Cada indicador vota CALL (+1), PUT (-1) ou neutro (0). A confianca e a forca
do consenso ponderada pela volatilidade: em mercado sem direcao (ATR baixo
relativo ao preco) o score e reduzido de proposito, porque sinal sem
tendencia e ruido com numero bonito em cima.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import indicators as ind


@dataclass
class Candle:
    ts: int          # epoch segundos
    open: float
    high: float
    low: float
    close: float


@dataclass
class Assessment:
    direction: str            # "call" | "put" | "flat"
    confidence: int           # 0-100
    score: float              # -1.0 .. 1.0
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "direction": self.direction,
            "confidence": self.confidence,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
            "metrics": self.metrics,
        }


MIN_CANDLES = 40


def evaluate(candles: list[Candle]) -> Assessment | None:
    """Avalia a serie. Retorna None se nao houver dados suficientes.

    Usa apenas velas fechadas (candles[:-1]) para prever o proximo candle.
    """
    if len(candles) < MIN_CANDLES + 1:
        return None

    closed = candles[:-1]
    closes = [c.close for c in closed]
    highs = [c.high for c in closed]
    lows = [c.low for c in closed]

    last = closes[-1]
    if last <= 0:
        return None

    votes: list[tuple[str, float, str]] = []

    # 1. Tendencia por cruzamento de EMAs
    ema_fast = ind.ema(closes, 9)
    ema_slow = ind.ema(closes, 21)
    if ema_fast is not None and ema_slow is not None:
        gap = (ema_fast - ema_slow) / last * 100.0
        weight = 1.4
        if gap > 0.01:
            votes.append(("call", weight, f"EMA9 acima da EMA21 (+{gap:.3f}%)"))
        elif gap < -0.01:
            votes.append(("put", weight, f"EMA9 abaixo da EMA21 ({gap:.3f}%)"))
        else:
            votes.append(("flat", weight, "EMAs sobrepostas"))

    # 2. RSI como filtro de exaustao
    r = ind.rsi(closes, 14)
    if r is not None:
        if r >= 62:
            votes.append(("call", 0.8, f"RSI {r:.1f} em zona de forca"))
        elif r <= 38:
            votes.append(("put", 0.8, f"RSI {r:.1f} em zona de fraqueza"))
        elif 45 <= r <= 55:
            votes.append(("flat", 0.5, f"RSI {r:.1f} neutro"))
        else:
            votes.append(("call" if r > 50 else "put", 0.3,
                          f"RSI {r:.1f} levemente direcional"))

    # 3. Posicao nas Bandas de Bollinger (reversao nos extremos)
    bb = ind.bollinger(closes, 20, 2.0)
    bb_pos = None
    if bb:
        mean, low_b, up_b = bb
        span = up_b - low_b
        if span > 0:
            bb_pos = (last - low_b) / span
            if bb_pos < 0.08:
                votes.append(("call", 0.9, "Preco no fundo da banda (reversao)"))
            elif bb_pos > 0.92:
                votes.append(("put", 0.9, "Preco no topo da banda (reversao)"))

    # 4. Inclinacao da serie recente
    s = ind.slope(closes, 10)
    if abs(s) > 0.002:
        votes.append(("call" if s > 0 else "put", 0.7,
                      f"Inclinacao de curto prazo {s:+.4f}%/barra"))

    if not votes:
        return None

    total_w = sum(w for _, w, _ in votes)
    raw = sum((1 if d == "call" else -1 if d == "put" else 0) * w
              for d, w, _ in votes) / total_w

    # Fator de volatilidade: sem movimento, o sinal nao merece confianca
    a = ind.atr(highs, lows, closes, 14)
    atr_pct = (a / last * 100.0) if a else 0.0
    vol_factor = max(0.35, min(1.0, atr_pct / 0.05))

    score = raw * vol_factor
    confidence = int(round(abs(score) * 100))

    if confidence < 1:
        direction = "flat"
    else:
        direction = "call" if score > 0 else "put"

    agreeing = [msg for d, _, msg in votes
                if (d == direction) or (d == "flat" and direction == "flat")]

    metrics = {
        "ema9": round(ema_fast, 6) if ema_fast else None,
        "ema21": round(ema_slow, 6) if ema_slow else None,
        "rsi14": round(r, 2) if r is not None else None,
        "atr_pct": round(atr_pct, 4),
        "slope_pct": round(s, 5),
        "bb_position": round(bb_pos, 3) if bb_pos is not None else None,
        "vol_factor": round(vol_factor, 3),
        "candles": len(candles),
    }

    return Assessment(
        direction=direction,
        confidence=confidence,
        score=score,
        reasons=agreeing,
        metrics=metrics,
    )
