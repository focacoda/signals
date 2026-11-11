"""Loop principal: avalia ativos, publica sinais e liquida resultados.

A ordem das operacoes aqui e o que garante integridade:
  1. avalia
  2. grava o sinal com opened_at = agora
  3. somente depois o sinal pode ser liquidado

Liquidacao usa o preco no instante do vencimento, consultado na mesma fonte
que gerou o sinal. Se a fonte nao responder, o sinal fica 'open' e e tentado
de novo -- nunca e fechado com preco inventado.

Ciclo de vida do sinal (ver config.py):
  1. MEDICAO  -- no ultimo minuto do candle, a confluencia comeca a ser
                 medida e precisa se manter.
  2. ALERTA   -- se ela sobrevive ate os ultimos ALERT_WINDOW segundos,
                 vira alerta. Alerta nao e sinal: nao ha operacao aberta.
  3. ABERTURA -- o sinal abre na virada exata do candle, com o preco de
                 fechamento do candle que acabou, e fecha um candle depois.

Cada ativo e avaliado uma vez por prazo (M5, M15). O prazo define o
timeframe das velas -- M5 analisa velas de 5 minutos. O M1 ficou de fora
porque a confluencia atual nao separa sinal de ruido em 60 segundos.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .. import store
from ..config import (ALERT_WINDOW_SECONDS, MEASURE_WINDOW_SECONDS,
                      MIN_CONFIDENCE_BY_EXPIRY, LOOKBACK,
                      OPEN_GRACE_SECONDS, SCAN_INTERVAL, SETTLE_GRACE,
                      TIMEFRAMES, cooldown_for)
from ..feeds.base import Asset
from ..feeds.registry import FeedRegistry, default_assets
from ..hub import Hub
from . import strategy

log = logging.getLogger("scanner")

STRATEGY_NAME = "devhub-confluence-v1"


def candle_close_ts(candle_ts: int, timeframe: int) -> int:
    """Instante em que o candle que ABRIU em `candle_ts` fecha."""
    return candle_ts + timeframe


class Scanner:
    def __init__(self, registry: FeedRegistry, hub: Hub) -> None:
        self.registry = registry
        self.hub = hub
        self.assets: list[Asset] = default_assets()
        self.expiries: list[int] = sorted(TIMEFRAMES)
        # chave: "SYMBOL:EXPIRY"
        self._cooldown: dict[str, float] = {}
        self._last_assessment: dict[str, dict] = {}
        # confluencia medida no ultimo minuto, aguardando confirmacao
        self._measured: dict[str, dict] = {}
        # confluencia confirmada, aguardando a virada do candle para abrir
        self._alerts: dict[str, dict] = {}
        self._prices: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.last_scan: float = 0.0
        self.errors: dict[str, str] = {}

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()

    # ---------- dados para o dashboard ----------

    def snapshot(self) -> dict:
        now = time.time()
        return {
            "assets": [a.as_dict() for a in self.assets],
            "prices": dict(self._prices),
            "assessments": dict(self._last_assessment),
            "alerts": {
                k: {
                    **v,
                    "seconds_to_open": round(v["boundary_ts"] - now, 1),
                }
                for k, v in self._alerts.items()
            },
            "feeds": self.registry.status(),
            "last_scan": self.last_scan,
            "errors": dict(self.errors),
            "timeframes": dict(TIMEFRAMES),
            "emit_windows": {
                exp: ALERT_WINDOW_SECONDS for exp in self.expiries},
            "measure_window": MEASURE_WINDOW_SECONDS,
            "alert_window": ALERT_WINDOW_SECONDS,
            "confidence_bands": [
                {"above": MIN_CONFIDENCE_BY_EXPIRY[exp], "expiry_min": exp}
                for exp in self.expiries
            ],
            "open_signals_count": store.open_signals_count(),
        }

    def asset_by_symbol(self, symbol: str) -> Asset | None:
        for a in self.assets:
            if a.symbol == symbol:
                return a
        return None

    # ---------- loop ----------

    async def _run(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            try:
                await self._scan_all()
                await self._open_due()
                await self._settle_due()
                await self.hub.broadcast("tick", self.snapshot())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("Erro no ciclo de varredura: %s", exc)
            elapsed = time.time() - started
            await asyncio.sleep(max(0.5, SCAN_INTERVAL - elapsed))

    async def _scan_all(self) -> None:
        for asset in self.assets:
            for expiry in self.expiries:
                try:
                    await self._scan_one(asset, expiry)
                except Exception as exc:
                    self.errors[asset.symbol] = (
                        f"{type(exc).__name__}: {exc}")
                    log.debug("Falha em %s M%d: %s",
                              asset.symbol, expiry, exc)
        self.last_scan = time.time()

    async def _scan_one(self, asset: Asset, expiry: int) -> None:
        """Mede a confluencia e, se ela se mantiver, levanta o alerta.

        Nao abre sinal: quem abre e `_open_due`, na virada do candle.
        """
        timeframe = TIMEFRAMES[expiry]
        feed = self.registry.for_asset(asset)
        candles = await feed.candles(asset, LOOKBACK + 1, timeframe)
        if not candles or len(candles) < strategy.MIN_CANDLES + 2:
            self.errors[asset.symbol] = "sem dados da fonte"
            return
        self.errors.pop(asset.symbol, None)

        current = candles[-1]
        now = time.time()
        seconds_to_close = candle_close_ts(current.ts, timeframe) - now
        key = f"{asset.symbol}:{expiry}"
        min_conf = MIN_CONFIDENCE_BY_EXPIRY.get(expiry, 100)

        # A avaliacao usa so velas fechadas; `evaluate` descarta a ultima.
        result = strategy.evaluate(candles)
        if result is None:
            return

        # Fora do ultimo minuto do candle: nao avalia, nao mede, nao mostra.
        # A varredura SO existe dentro da janela de medicao. Antes disso
        # qualquer leitura e ruido; depois do fechamento ja e tarde demais.
        if seconds_to_close > MEASURE_WINDOW_SECONDS or seconds_to_close < -OPEN_GRACE_SECONDS:
            self._last_assessment.pop(key, None)
            self._measured.pop(key, None)
            return

        phase = ("alerta" if seconds_to_close <= ALERT_WINDOW_SECONDS
                 else "medindo")

        self._last_assessment[key] = {
            **result.as_dict(),
            "expiry_min": expiry,
            "timeframe_sec": timeframe,
            "seconds_to_close": round(seconds_to_close, 1),
            "emit_window": ALERT_WINDOW_SECONDS,
            "phase": phase,
        }
        if seconds_to_close < -OPEN_GRACE_SECONDS:
            self._measured.pop(key, None)
            return

        # Passa o piso? Se nao, a medicao e descartada -- precisa ser
        # continua, nao um pico isolado no meio do ultimo minuto.
        if (result.direction == "flat" or result.confidence < min_conf):
            self._measured.pop(key, None)
            return

        measured = self._measured.get(key)
        same_candle = measured is not None and measured["candle_ts"] == current.ts
        same_dir = same_candle and measured["direction"] == result.direction
        if not same_dir:
            # primeira leitura do ultimo minuto, ou o mercado reverteu:
            # (re)comeca a contagem
            self._measured[key] = {
                "direction": result.direction,
                "confidence": result.confidence,
                "candle_ts": current.ts,
                "since": now,
            }
            return

        # Medicao sobreviveu ate a janela de alerta?
        if phase != "alerta" or key in self._alerts:
            return
        # So abre se nao houver NENHUM sinal aberto neste ativo (qualquer prazo).
        # Isso evita que M5 e M15 disparem ao mesmo tempo no mesmo par.
        if store.has_open_signal(asset.symbol):
            return
        if now - self._cooldown.get(key, 0.0) < cooldown_for(expiry):
            return

        # Reconfirma com dados frescos: o alerta so existe se a confluencia
        # ainda estiver de pe neste instante, nao dez segundos atras.
        fresh = await feed.candles(asset, LOOKBACK + 1, timeframe)
        if not fresh or len(fresh) < strategy.MIN_CANDLES + 2:
            return
        check = strategy.evaluate(fresh)
        if (check is None or check.direction != measured["direction"]
                or check.confidence < min_conf):
            self._measured.pop(key, None)
            return

        boundary = candle_close_ts(current.ts, timeframe)
        self._alerts[key] = {
            "symbol": asset.symbol,
            "market": asset.market,
            "source": asset.source,
            "verified": asset.verified,
            "direction": check.direction,
            "expiry_min": expiry,
            "timeframe_sec": timeframe,
            "confidence": check.confidence,
            "score": check.score,
            "reasons": check.reasons,
            "metrics": check.metrics,
            "boundary_ts": boundary,
            "expires_at": boundary + expiry * 60,
            "measured_since": measured["since"],
            "confirmed_at": now,
        }
        await self.hub.broadcast("alert", self._alerts[key])
        log.info("Alerta %s M%d %s conf=%s -- abre em %ds",
                 asset.symbol, expiry, check.direction, check.confidence,
                 max(0, int(boundary - now)))

    # ---------- abertura na virada do candle ----------

    async def _open_due(self) -> None:
        """Abre os alertas confirmados cujo candle ja virou.

        A entrada e o fechamento do candle que acabou de fechar -- o preco
        exato da virada. Nunca o preco andando depois dela.
        """
        if not self._alerts:
            return
        now = time.time()
        for key in list(self._alerts):
            alert = self._alerts[key]
            boundary = alert["boundary_ts"]
            if boundary > now:
                continue
            if now - boundary > OPEN_GRACE_SECONDS:
                log.warning("Alerta %s expirou sem preco de entrada", key)
                self._alerts.pop(key, None)
                self._measured.pop(key, None)
                continue

            asset = self.asset_by_symbol(alert["symbol"])
            if asset is None:
                self._alerts.pop(key, None)
                continue
            timeframe = alert["timeframe_sec"]
            feed = self.registry.for_asset(asset)
            candles = await feed.candles(asset, LOOKBACK + 2, timeframe)
            if not candles:
                continue
            # o candle que fechou exatamente na virada
            entry_candle = None
            for c in candles:
                if c.ts == boundary - timeframe:
                    entry_candle = c
                    break
            if entry_candle is None:
                # a fonte ainda nao entregou o candle fechado; tenta de novo
                continue

            expiry = alert["expiry_min"]
            # Um sinal aberto por ativo, qualquer prazo: dois no mesmo par
            # (um M5 e um M15) seriam duas apostas no mesmo preco.
            if store.has_open_signal(asset.symbol):
                self._alerts.pop(key, None)
                self._measured.pop(key, None)
                continue

            payload = {
                "symbol": asset.symbol,
                "market": asset.market,
                "source": asset.source,
                "verified": asset.verified,
                "strategy": STRATEGY_NAME,
                "direction": alert["direction"],
                "expiry_min": expiry,
                "timeframe_sec": timeframe,
                "entry_price": entry_candle.close,
                "confidence": alert["confidence"],
                "score": alert["score"],
                "reasons": alert["reasons"],
                "metrics": alert["metrics"],
                "opened_at": boundary,
                "expires_at": boundary + expiry * 60,
            }
            sig_id = store.insert_signal(payload)
            self._cooldown[key] = now
            self._alerts.pop(key, None)
            self._measured.pop(key, None)
            payload["id"] = sig_id
            payload["status"] = "open"
            await self.hub.broadcast("signal", payload)
            log.info("Sinal #%s %s M%d %s conf=%s entrada=%s",
                     sig_id, asset.symbol, expiry, alert["direction"],
                     alert["confidence"], entry_candle.close)

    # ---------- liquidacao ----------

    async def _settle_due(self) -> None:
        """Liquida pelo fechamento da vela no instante do vencimento.

        O preco de saida NAO e o preco corrente: e o fechamento da vela cujo
        fim coincide com `expires_at`. Duas razoes:
          - o preco corrente pode estar defasado ou ausente no exato instante
            do vencimento, e liquidar com ele mede o momento errado;
          - se a fonte nao responder, inventar um preco (empate artificial)
            contamina o track record com resultados que nao aconteceram.

        Quando o candle de vencimento ainda nao chegou, o sinal continua
        aberto e e tentado de novo no proximo ciclo. Nada e fechado sem o
        preco real.
        """
        now = time.time()
        due = store.pending_settlement(now - SETTLE_GRACE)
        for row in due:
            asset = self.asset_by_symbol(row["symbol"])
            if asset is None:
                continue
            feed = self.registry.for_asset(asset)
            timeframe = TIMEFRAMES.get(int(row["expiry_min"]), 60)
            expires_at = float(row["expires_at"])

            # A vela que fecha em `expires_at` abriu `timeframe` antes.
            candles = await feed.candles(asset, LOOKBACK + 2, timeframe)
            exit_candle = None
            for c in candles or []:
                if candle_close_ts(c.ts, timeframe) == int(expires_at):
                    exit_candle = c
                    break

            if exit_candle is None:
                # A fonte ainda nao publicou a vela de vencimento. Mantem
                # aberto e tenta no proximo ciclo -- mas nao para sempre:
                # passado o limite, o sinal e anulado em vez de ficar preso.
                if now - expires_at > SETTLE_GRACE * 20:
                    store.settle(row["id"], "void", None, now)
                    log.warning("Sinal #%s anulado: sem vela de vencimento",
                                row["id"])
                continue

            exit_price = float(exit_candle.close)
            entry = float(row["entry_price"])
            direction = row["direction"]
            if abs(exit_price - entry) < 1e-12:
                outcome = "tie"
            elif direction == "call":
                outcome = "win" if exit_price > entry else "loss"
            else:
                outcome = "win" if exit_price < entry else "loss"
            store.settle(row["id"], outcome, exit_price, now)
            await self.hub.broadcast("settled", {
                "id": row["id"], "symbol": row["symbol"],
                "direction": direction, "entry_price": entry,
                "exit_price": exit_price, "result": outcome,
                "confidence": row["confidence"],
            })
