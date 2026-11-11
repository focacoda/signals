"""Conector IQ Option via iqoptionapi (fork lukefeix).

Login real por e-mail/senha, velas reais dos ativos em qualquer timeframe
operado (M5, M15). Cobre forex, cripto e OTC -- todos pela mesma sessao.

O mapa de ativos -> codigo numerico NAO e escrito a mao: a cada sessao ele e
lido do proprio servidor (`get_ALL_Binary_ACTIVES_OPCODE`), e a lista de
simbolos vem do catalogo de ativos. A tabela estatica da biblioteca envelhece
e ja estava errada em varios pares.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

from ..config import IQ_EMAIL, IQ_ENABLED, IQ_PASSWORD
from .base import Asset, Feed
from ..engine.strategy import Candle

log = logging.getLogger("iq")

_VENDOR = Path(__file__).resolve().parents[2] / "vendor" / "iqoptionapi-master"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

# Codigos usados enquanto o servidor nao respondeu. Cobrem so os pares que
# ja existiam antes; o mapa real vem do servidor no login e substitui isto.
_FALLBACK_IDS = {
    "EURUSD": 1, "EURGBP": 2, "GBPJPY": 3, "EURJPY": 4, "GBPUSD": 5,
    "USDJPY": 6, "NZDUSD": 8, "USDCHF": 72, "AUDUSD": 99, "USDCAD": 100,
    "BTCUSD": 816, "ETHUSD": 818,
    # OTC (nomes com hifen, como a IQ usa)
    "EURUSD-OTC": 76, "EURGBP-OTC": 77, "USDCHF-OTC": 78,
    "EURJPY-OTC": 79, "NZDUSD-OTC": 80, "GBPUSD-OTC": 81,
    "GBPJPY-OTC": 84, "USDJPY-OTC": 85, "AUDUSD-OTC": 2111,
    "USDCAD-OTC": 2112, "ETHUSD-OTC": 1941,
    "XAUUSD-OTC": 1857, "XAGUSD-OTC": 1858,
}


class IQFeed:
    name = "iq"

    def __init__(self) -> None:
        self.configured = bool(
            IQ_ENABLED and IQ_EMAIL and IQ_PASSWORD)
        self.available = False
        self._api = None
        self._last_error: str | None = None
        self._ids: dict[str, int] = dict(_FALLBACK_IDS)
        self._lock = asyncio.Lock()

    # ---------- sessao ----------

    def _login(self) -> bool:
        from iqoptionapi.stable_api import IQ_Option
        api = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
        ok, reason = api.connect()
        if not ok:
            self._last_error = str(reason)
            return False
        self._api = api
        self._load_actives(api)
        return True

    def _load_actives(self, api) -> None:
        """Le o mapa simbolo -> codigo direto do servidor.

        Falha aqui nao derruba a sessao: mantem o fallback e registra o
        motivo, porque perder o mapa nao e motivo para parar de operar.
        """
        try:
            api.get_ALL_Binary_ACTIVES_OPCODE()
            import iqoptionapi.constants as OP_code
            found = {s: int(OP_code.ACTIVES[s])
                     for s in SYMBOLS if s in OP_code.ACTIVES}
            if found:
                self._ids = found
                missing = [s for s in SYMBOLS if s not in found]
                if missing:
                    log.warning("Ativos sem codigo na IQ: %s",
                                ", ".join(missing))
        except Exception as exc:
            log.warning("Nao consegui ler o mapa de ativos: %s", exc)

    async def _connect(self) -> bool:
        if not self.configured:
            return False
        async with self._lock:
            if self.available and self._api is not None:
                return True
            try:
                ok = await asyncio.to_thread(self._login)
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                return False
            self.available = ok
            if ok:
                self._last_error = None
            return ok

    async def close(self) -> None:
        api, self._api = self._api, None
        self.available = False
        if api is not None:
            try:
                await asyncio.to_thread(api.close)
            except Exception:
                pass

    # ---------- dados ----------

    async def candles(self, asset, limit: int = 120,
                      timeframe: int = 60) -> list[Candle]:
        # Usa o nome exato da corretora (ex: "EURUSD-OTC") se disponivel;
        # senao fallback para o simbolo padrao do sistema.
        symbol = getattr(asset, "canonical", None) or getattr(asset, "symbol", asset)
        if not await self._connect():
            return []
        if symbol not in self._ids:
            return []
        api = self._api
        if api is None:
            return []
        try:
            raw = await asyncio.to_thread(
                api.get_candles, symbol, int(timeframe), limit,
                int(time.time()))
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            self.available = False
            self._api = None
            return []
        if not raw:
            return []

        out: list[Candle] = []
        for c in raw:
            try:
                out.append(Candle(
                    ts=int(c["from"]),
                    open=float(c["open"]),
                    high=float(c["max"]),
                    low=float(c["min"]),
                    close=float(c["close"]),
                ))
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
        out.sort(key=lambda k: k.ts)
        return out

    async def price(self, asset: Asset) -> float | None:
        """Preco corrente do ativo, usado na liquidacao.

        Prefere o stream em tempo real, que entrega o ultimo negocio. Ele
        depende de assinatura por simbolo, entao se nao estiver ativo cai
        para a vela de M1 corrente -- pior (ate 60s de atraso) mas nunca
        inexistente. Liquidar com preco defasado e melhor que nao liquidar,
        e o erro do M1 e pequeno frente ao vencimento que esta sendo medido.
        """
        # Mesma regra de `candles`: o nome na corretora e o `canonical`
        # ("EURUSD-OTC"). Usar `symbol` ("EURUSD_OTC") aqui nunca acerta.
        symbol = getattr(asset, "canonical", None) or getattr(
            asset, "symbol", asset)
        if not await self._connect():
            return None
        api = self._api
        aid = self._ids.get(symbol)
        if api is None or aid is None:
            return None

        try:
            live = await asyncio.to_thread(self._live_price, api, aid)
            if live is not None:
                return live
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"

        try:
            raw = await asyncio.to_thread(
                api.get_candles, symbol, 60, 2, int(time.time()))
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            return None
        if not raw:
            return None
        try:
            latest = max(raw, key=lambda c: int(c["from"]))
            return float(latest["close"])
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            return None

    @staticmethod
    def _live_price(api, active_id: int) -> float | None:
        """Ultimo preco do stream de tempo real, ou None se nao assinado."""
        rt = api.get_realtime_candles(active_id, 60)
        if not rt:
            try:
                api.start_candles_stream(active_id, 60, 1)
            except Exception:
                return None
            rt = api.get_realtime_candles(active_id, 60)
        if not rt:
            return None
        latest = max(rt.values(), key=lambda c: int(c["from"]))
        return float(latest["close"])

    def status(self) -> dict:
        return {
            "configured": self.configured,
            "available": self.available,
            "error": self._last_error,
            "actives": len(self._ids),
        }
