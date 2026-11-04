"""Servidor FastAPI: dashboard, API REST e WebSocket."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import store
from .config import CONFIDENCE_BANDS, EXPIRIES, MIN_CONFIDENCE, SCAN_INTERVAL
from .engine import calc, strategy
from .engine.scanner import STRATEGY_NAME, Scanner
from .feeds.registry import FeedRegistry
from .hub import Hub

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)-10s %(message)s",
    datefmt="%H:%M:%S")
log = logging.getLogger("app")

STATIC_DIR = Path(__file__).parent / "static"

registry = FeedRegistry()
hub = Hub()
scanner = Scanner(registry, hub)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init()
    await scanner.start()
    log.info("Motor iniciado: %d ativos, varredura a cada %ds",
             len(scanner.assets), SCAN_INTERVAL)
    yield
    await scanner.stop()
    await registry.close()


app = FastAPI(
    title="DevHub Signals",
    version="1.0.0",
    description=(
        "Plataforma de sinais com track record auditavel: todo sinal e "
        "gravado antes do resultado existir."),
    lifespan=lifespan,
)


# ---------- meta ----------

@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "strategy": STRATEGY_NAME,
        "assets": len(scanner.assets),
        "feeds": registry.status(),
        "ws_clients": hub.client_count,
        "signals_recorded": store.count(),
        "scan_interval": SCAN_INTERVAL,
        "min_confidence": MIN_CONFIDENCE,
        "expiries": EXPIRIES,
        "confidence_bands": [
            {"above": minimo, "expiry_min": exp}
            for minimo, exp in CONFIDENCE_BANDS
        ],
    }


@app.get("/api/assets")
async def assets() -> dict:
    snap = scanner.snapshot()
    return {"assets": snap["assets"], "prices": snap["prices"],
            "assessments": snap["assessments"], "feeds": snap["feeds"]}


@app.get("/api/snapshot")
async def snapshot() -> dict:
    return scanner.snapshot()


# ---------- sinais ----------

@app.get("/api/signals")
async def signals(limit: int = Query(50, ge=1, le=500),
                  symbol: str | None = None) -> dict:
    if symbol:
        return {"signals": store.by_symbol(symbol.upper(), limit)}
    return {"signals": store.recent(limit)}


@app.get("/api/signals/open")
async def open_signals() -> dict:
    return {"signals": store.open_signals()}


@app.get("/api/stats")
async def stats(symbol: str | None = None, market: str | None = None) -> dict:
    return store.stats(symbol, market)


# ---------- backtest e calculadoras ----------

class BacktestBody(BaseModel):
    symbol: str = "BTCUSD"
    expiry_min: int = Field(5, ge=1, le=60)
    min_confidence: int = Field(60, ge=1, le=99)
    payout_pct: float = Field(85.0, gt=0, le=500)
    bars: int = Field(1000, ge=200, le=5000)


@app.post("/api/backtest")
async def run_backtest(body: BacktestBody) -> dict:
    asset = scanner.asset_by_symbol(body.symbol.upper())
    if asset is None:
        raise HTTPException(404, f"ativo desconhecido: {body.symbol}")
    feed = registry.for_asset(asset)
    candles = await feed.candles(asset, body.bars)
    if not candles or len(candles) < strategy.MIN_CANDLES + body.expiry_min:
        raise HTTPException(
            503, f"dados insuficientes para {asset.symbol} "
                 f"(recebidos {len(candles)} candles)")
    # O replay e O(n^2) em Python puro. Rodar isso direto no handler async
    # bloqueia o event loop e congela o WebSocket do dashboard enquanto
    # calcula. Por isso vai para uma thread.
    out = await asyncio.to_thread(
        calc.backtest, candles, body.expiry_min, body.min_confidence,
        body.payout_pct)
    out["symbol"] = asset.symbol
    out["source"] = asset.source
    out["verified"] = asset.verified
    out["candles"] = len(candles)
    return out


@app.get("/api/pip-value")
async def pip_value(pair: str = "EURUSD", lots: float = 1.0,
                    account_currency: str = "USD",
                    price: float = 1.0) -> dict:
    return calc.pip_value(pair, lots, account_currency, price)


@app.get("/api/binary-staking")
async def binary_staking(balance: float = 1000.0, payout_pct: float = 85.0,
                         win_rate_pct: float = 60.0,
                         risk_pct: float = 2.0) -> dict:
    return calc.binary_staking(balance, payout_pct, win_rate_pct, risk_pct)


@app.get("/api/drawdown-recovery")
async def drawdown_recovery(drawdown_pct: float = 20.0) -> dict:
    return calc.drawdown_recovery(drawdown_pct)


@app.get("/api/margin")
async def margin(notional: float = 10000.0, leverage: float = 100.0) -> dict:
    return calc.margin_leverage(notional, leverage)


class AverageCostBody(BaseModel):
    entries: list[tuple[float, float]]


@app.post("/api/average-cost")
async def average_cost(body: AverageCostBody) -> dict:
    if not body.entries:
        raise HTTPException(400, "informe ao menos uma entrada")
    return calc.average_cost(body.entries)


class RiskBody(BaseModel):
    balance: float = Field(10000, gt=0)
    daily_dd_pct: float = Field(5, gt=0, lt=100)
    max_dd_pct: float = Field(10, gt=0, lt=100)
    risk_per_trade_pct: float = Field(1, gt=0, lt=100)
    payout_pct: float = Field(85, gt=0, le=500)
    win_rate_pct: float = Field(60, ge=0, le=100)


@app.post("/api/risk-plan")
async def risk_plan(body: RiskBody) -> dict:
    return calc.risk_plan(
        body.balance, body.daily_dd_pct, body.max_dd_pct,
        body.risk_per_trade_pct, body.payout_pct, body.win_rate_pct)


# ---------- websocket ----------

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    await hub.register(ws)
    try:
        await ws.send_json({"type": "tick", "data": scanner.snapshot()})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.unregister(ws)


# ---------- dashboard ----------

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
