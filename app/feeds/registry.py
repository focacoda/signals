"""Catalogo de ativos e resolucao de feed por ativo.

Fonte unica: IQ Option. Forex, cripto e OTC vem todos da mesma sessao
autenticada -- inclusive o OTC, que antes era gerado por nos e agora usa
as velas reais da corretora.
"""
from __future__ import annotations

from .base import Asset, Feed
from .iq import IQFeed


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

    # OTC: ativos da PROPRIA IQ Option, com velas reais da corretora.
    #
    # O nome na IQ usa hifen ("EURUSD-OTC"), por isso `canonical` guarda o
    # nome da corretora e `symbol` mantem o formato do sistema. Nao ha mais
    # preco gerado por nos: o que aparece na tela e o que a IQ negocia, e o
    # resultado de um sinal sai do fechamento real da vela.
    for sym, canonical, name in [
        ("EURUSD_OTC", "EURUSD-OTC", "Euro / Dolar OTC"),
        ("GBPUSD_OTC", "GBPUSD-OTC", "Libra / Dolar OTC"),
        ("USDJPY_OTC", "USDJPY-OTC", "Dolar / Iene OTC"),
        ("AUDUSD_OTC", "AUDUSD-OTC", "Dolar Aus / Dolar OTC"),
        ("USDCAD_OTC", "USDCAD-OTC", "Dolar / Canadense OTC"),
        ("NZDUSD_OTC", "NZDUSD-OTC", "Dolar NZ / Dolar OTC"),
        ("EURJPY_OTC", "EURJPY-OTC", "Euro / Iene OTC"),
        ("GBPJPY_OTC", "GBPJPY-OTC", "Libra / Iene OTC"),
        ("EURGBP_OTC", "EURGBP-OTC", "Euro / Libra OTC"),
        ("USDCHF_OTC", "USDCHF-OTC", "Dolar / Franco OTC"),
        ("ETHUSD_OTC", "ETHUSD-OTC", "Ethereum OTC"),
        ("XAUUSD_OTC", "XAUUSD-OTC", "Ouro / Dolar OTC"),
        ("XAGUSD_OTC", "XAGUSD-OTC", "Prata / Dolar OTC"),
    ]:
        assets.append(Asset(
            symbol=sym, name=name, market="otc", source="iq",
            canonical=canonical, payout=82, verified=True))

    return assets


class FeedRegistry:
    def __init__(self) -> None:
        self.iq = IQFeed()
        self._by_name: dict[str, Feed] = {
            "iq": self.iq,
        }

    def for_asset(self, asset: Asset) -> Feed:
        return self._by_name[asset.source]

    def status(self) -> dict:
        return {"iq": self.iq.status()}

    async def close(self) -> None:
        await self.iq.close()
