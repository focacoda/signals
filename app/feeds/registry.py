"""Catalogo de ativos e resolucao de feed por ativo."""
from __future__ import annotations

from .base import Asset, Feed
from .binance import BinanceFeed
from .iq import IQFeed
from .otc_sim import OTCSimFeed


def default_assets() -> list[Asset]:
    assets: list[Asset] = []

    # Cripto: dados reais publicos, resultado auditavel por terceiro
    for sym, name in [
        ("BTCUSDT", "Bitcoin"), ("ETHUSDT", "Ethereum"),
        ("SOLUSDT", "Solana"), ("BNBUSDT", "BNB"),
        ("XRPUSDT", "XRP"), ("DOGEUSDT", "Dogecoin"),
    ]:
        assets.append(Asset(
            symbol=sym.replace("USDT", "USD"), name=name, market="crypto",
            source="binance", canonical=sym, payout=87, verified=True))

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
        self.binance = BinanceFeed()
        self.iq = IQFeed()
        self.otc = OTCSimFeed()
        self._by_name: dict[str, Feed] = {
            "binance": self.binance,
            "iq": self.iq,
            "sim_otc": self.otc,
        }

    def for_asset(self, asset: Asset) -> Feed:
        return self._by_name[asset.source]

    def status(self) -> dict:
        return {
            "binance": {"available": self.binance.available,
                        "configured": True},
            "iq": self.iq.status(),
            "sim_otc": {"available": True, "configured": True},
        }

    async def close(self) -> None:
        await self.binance.close()
        await self.iq.close()
        await self.otc.close()
