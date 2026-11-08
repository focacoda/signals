"""Catalogo de ativos e resolucao de feed por ativo.

Fonte unica: IQ Option. A Binance foi removida; cripto agora tambem vem da
IQ Option, entao todo ativo do sistema usa a mesma sessao autenticada.
"""
from __future__ import annotations

from .base import Asset, Feed
from .iq import IQFeed
from .otc_sim import OTCSimFeed


def default_assets() -> list[Asset]:
    assets: list[Asset] = []

    # Cripto: somente os ativos que a IQ Option assina de fato
    for sym, name in [
        ("BTCUSD", "Bitcoin"), ("ETHUSD", "Ethereum"),
    ]:
        assets.append(Asset(
            symbol=sym, name=name, market="crypto",
            source="iq", canonical=sym, payout=87, verified=True))

    # Forex: pela IQ Option quando configurada, senao fora do radar
    for sym, name in [
        ("EURUSD", "Euro / Dolar"), ("GBPUSD", "Libra / Dolar"),
        ("USDJPY", "Dolar / Iene"), ("AUDUSD", "Dolar Australiano"),
        ("USDCAD", "Dolar / Canadense"), ("EURJPY", "Euro / Iene"),
        ("GBPJPY", "Libra / Iene"), ("NZDUSD", "Dolar NZ / Dolar"),
    ]:
        assets.append(Asset(
            symbol=sym, name=name, market="forex", source="iq",
            canonical=sym, payout=84, verified=True))

    # OTC sintetico: nao auditavel por terceiro, marcado como tal
    for sym, name in [
        ("EURUSD_OTC", "Euro / Dolar OTC"),
        ("GBPUSD_OTC", "Libra / Dolar OTC"),
        ("USDJPY_OTC", "Dolar / Iene OTC"),
        ("AUDUSD_OTC", "Dolar Aus / Dolar OTC"),
        ("USDCAD_OTC", "Dolar / Canadense OTC"),
        ("NZDUSD_OTC", "Dolar NZ / Dolar OTC"),
        ("EURJPY_OTC", "Euro / Iene OTC"),
        ("GBPJPY_OTC", "Libra / Iene OTC"),
        ("XAUUSD_OTC", "Ouro / Dolar OTC"),
        ("XAGUSD_OTC", "Prata / Dolar OTC"),
    ]:
        assets.append(Asset(
            symbol=sym, name=name, market="otc", source="sim_otc",
            canonical=sym, payout=82, verified=False))

    return assets


class FeedRegistry:
    def __init__(self) -> None:
        self.iq = IQFeed()
        self.otc = OTCSimFeed()
        self._by_name: dict[str, Feed] = {
            "iq": self.iq,
            "sim_otc": self.otc,
        }

    def for_asset(self, asset: Asset) -> Feed:
        return self._by_name[asset.source]

    def status(self) -> dict:
        return {
            "iq": self.iq.status(),
            "sim_otc": {"available": True, "configured": True},
        }

    async def close(self) -> None:
        await self.iq.close()
        await self.otc.close()
