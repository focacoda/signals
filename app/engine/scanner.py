"""Loop principal: avalia ativos, publica sinais e liquida resultados.

A ordem das operacoes aqui e o que garante integridade:
  1. avalia
  2. grava o sinal com opened_at = agora
  3. somente depois o sinal pode ser liquidado

Liquidacao usa o preco no instante do vencimento, consultado na mesma fonte
que gerou o sinal. Se a fonte nao responder, o sinal fica 'open' e e tentado
de novo -- nunca e fechado com preco inventado.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .. import store
from ..config import (CONFIDENCE_BANDS, COOLDOWN_SECONDS, LOOKBACK,
                      MIN_CONFIDENCE, SCAN_INTERVAL, SETTLE_GRACE)
from ..feeds.base import Asset
from ..feeds.registry import FeedRegistry, default_assets
from ..hub import Hub
from . import strategy

log = logging.getLogger("scanner")

STRATEGY_NAME = "devhub-confluence-v1"


class Scanner:
    def __init__(self, registry: FeedRegistry, hub: Hub) -> None:
        self.registry = registry
        self.hub = hub
        self.assets: list[Asset] = default_assets()
        self._cooldown: dict[str, float] = {}
        self._last_assessment: dict[str, dict] = {}
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
        return {
            "assets": [a.as_dict() for a in self.assets],
            "prices": dict(self._prices),
            "assessments": dict(self._last_assessment),
            "feeds": self.registry.status(),
            "last_scan": self.last_scan,
            "errors": dict(self.errors),
            "confidence_bands": [
                {"above": minimo, "expiry_min": exp}
                for minimo, exp in CONFIDENCE_BANDS
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
            try:
                await self._scan_one(asset)
            except Exception as exc:
                self.errors[asset.symbol] = f"{type(exc).__name__}: {exc}"
                log.debug("Falha em %s: %s", asset.symbol, exc)
        self.last_scan = time.time()

    async def _scan_one(self, asset: Asset) -> None:
        feed = self.registry.for_asset(asset)
        candles = await feed.candles(asset, LOOKBACK)
        if not candles:
            self.errors[asset.symbol] = "sem dados da fonte"
            return
        self.errors.pop(asset.symbol, None)

        live = await feed.price(asset)
        self._prices[asset.symbol] = live or candles[-1].close

        result = strategy.evaluate(candles)
        if result is None:
            return
        self._last_assessment[asset.symbol] = result.as_dict()

        now = time.time()
        if result.direction == "flat":
            return
        if result.confidence < MIN_CONFIDENCE:
            return
        last = self._cooldown.get(asset.symbol, 0.0)
        if now - last < COOLDOWN_SECONDS:
            return

        # Verifica se ja existe sinal aberto para este ativo
        if store.has_open_signal(asset.symbol):
            log.debug("Pulando %s: ja possui sinal aberto", asset.symbol)
            return

        expiry = self._pick_expiry(result.confidence)
        if expiry is None:
            return
        entry = live or candles[-1].close
        payload = {
            "symbol": asset.symbol,
            "market": asset.market,
            "source": asset.source,
            "verified": asset.verified,
            "strategy": STRATEGY_NAME,
            "direction": result.direction,
            "expiry_min": expiry,
            "entry_price": entry,
            "confidence": result.confidence,
            "score": result.score,
            "reasons": result.reasons,
            "metrics": result.metrics,
            "opened_at": now,
            "expires_at": now + expiry * 60,
        }
        sig_id = store.insert_signal(payload)
        self._cooldown[asset.symbol] = now
        payload["id"] = sig_id
        payload["status"] = "open"
        # Rele do banco: e a fonte da verdade, nao o dict em memoria
        await self.hub.broadcast("signal", payload)
        log.info("Sinal #%s %s %s conf=%s", sig_id, asset.symbol,
                 result.direction, result.confidence)

    @staticmethod
    def _pick_expiry(confidence: int) -> int | None:
        """Prazo pelo nivel de confianca. None = nao emite sinal.

        """
        for minimo, expiracao in CONFIDENCE_BANDS:
            if confidence >= minimo:
                return expiracao
        return None

    # ---------- liquidacao ----------

    async def _settle_due(self) -> None:
        due = store.pending_settlement(time.time() - SETTLE_GRACE)
        for row in due:
            asset = self.asset_by_symbol(row["symbol"])
            if asset is None:
                continue
            feed = self.registry.for_asset(asset)
            exit_price = await feed.price(asset)
            if exit_price is None:
                continue
            entry = float(row["entry_price"])
            direction = row["direction"]
            if abs(exit_price - entry) < 1e-12:
                outcome = "tie"
            elif direction == "call":
                outcome = "win" if exit_price > entry else "loss"
            else:
                outcome = "win" if exit_price < entry else "loss"
            store.settle(row["id"], outcome, exit_price, time.time())
            await self.hub.broadcast("settled", {
                "id": row["id"], "symbol": row["symbol"],
                "direction": direction, "entry_price": entry,
                "exit_price": exit_price, "result": outcome,
                "confidence": row["confidence"],
            })
