"""Calculadoras de risco. Funcoes puras, sem I/O."""
from __future__ import annotations

# ---------- calculadoras ----------


def pip_value(pair: str, lots: float, account_currency: str = "USD",
              price: float = 1.0) -> dict:
    """Valor do pip. Convencao: 1 lote = 100.000 unidades."""
    pair = pair.upper().replace("/", "")
    jpy_quote = pair.endswith("JPY")
    pip = 0.01 if jpy_quote else 0.0001
    units = lots * 100_000
    raw = units * pip
    # Se a moeda de cotacao nao for a da conta, converte pelo preco informado
    quote = pair[-3:]
    if quote == account_currency:
        value = raw
    elif account_currency == "USD" and quote == "USD":
        value = raw
    elif account_currency == "USD" and price > 0:
        value = raw / price
    else:
        value = raw
    return {
        "pair": pair,
        "lots": lots,
        "units": units,
        "pip_size": pip,
        "pip_value": round(value, 4),
        "account_currency": account_currency,
        "note": ("Par com JPY: pip e a segunda decimal." if jpy_quote
                 else "Par padrao: pip e a quarta decimal."),
    }


def binary_staking(balance: float, payout_pct: float,
                   win_rate_pct: float, risk_pct: float = 2.0) -> dict:
    """Quanto apostar por operacao em binarias.

    Em binarias o payoff e assimetrico: voce arrisca 100% do stake para
    ganhar payout%. Isso da um ponto de equilibrio que depende do payout --
    win rate abaixo dele e prejuizo mesmo acertando muito.
    """
    if payout_pct <= 0:
        raise ValueError("payout deve ser maior que zero")
    break_even = 100.0 / (100.0 + payout_pct) * 100.0
    stake = balance * risk_pct / 100.0
    expected = (win_rate_pct / 100.0) * stake * (payout_pct / 100.0) \
        - (1 - win_rate_pct / 100.0) * stake
    return {
        "balance": balance,
        "payout_pct": payout_pct,
        "win_rate_pct": win_rate_pct,
        "risk_pct": risk_pct,
        "stake": round(stake, 2),
        "break_even_win_rate": round(break_even, 2),
        "edge_pct_points": round(win_rate_pct - break_even, 2),
        "expected_value_per_trade": round(expected, 2),
        "profitable": expected > 0,
        "note": (f"Com payout de {payout_pct:.0f}% voce precisa acertar "
                 f"mais de {break_even:.1f}% apenas para empatar."),
    }


def drawdown_recovery(drawdown_pct: float) -> dict:
    """Ganho necessario para voltar ao ponto de partida."""
    if drawdown_pct <= 0:
        return {"drawdown_pct": 0.0, "recovery_pct": 0.0,
                "remaining_equity_pct": 100.0, "note": "Sem drawdown."}
    if drawdown_pct >= 100:
        return {"drawdown_pct": 100.0, "recovery_pct": None,
                "remaining_equity_pct": 0.0,
                "note": "Conta zerada: nao ha recuperacao possivel."}
    remaining = 100.0 - drawdown_pct
    recovery = drawdown_pct / remaining * 100.0
    return {
        "drawdown_pct": drawdown_pct,
        "remaining_equity_pct": round(remaining, 2),
        "recovery_pct": round(recovery, 2),
        "note": (f"Perder {drawdown_pct:.1f}% exige ganhar {recovery:.1f}% "
                 f"sobre o saldo restante para voltar ao inicio."),
    }


def margin_leverage(notional: float, leverage: float) -> dict:
    if leverage <= 0:
        raise ValueError("alavancagem deve ser maior que zero")
    return {
        "notional": notional,
        "leverage": leverage,
        "margin_required": round(notional / leverage, 2),
        "note": f"1:{leverage:.0f} significa {leverage:.0f}x de exposicao.",
    }


def average_cost(entries: list[tuple[float, float]]) -> dict:
    """entries: lista de (quantidade, preco)."""
    qty = sum(q for q, _ in entries)
    if qty <= 0:
        raise ValueError("quantidade total deve ser maior que zero")
    cost = sum(q * p for q, p in entries)
    return {
        "total_quantity": round(qty, 8),
        "total_cost": round(cost, 2),
        "average_price": round(cost / qty, 8),
    }


# ---------- gestao de risco / prop firm ----------


def risk_plan(balance: float, daily_dd_pct: float, max_dd_pct: float,
              risk_per_trade_pct: float, payout_pct: float,
              win_rate_pct: float) -> dict:
    """Plano de operacao com limites de drawdown no estilo prop firm."""
    daily_limit = balance * daily_dd_pct / 100.0
    max_limit = balance * max_dd_pct / 100.0
    stake = balance * risk_per_trade_pct / 100.0
    per_trade_loss = stake
    trades_until_daily = int(daily_limit // per_trade_loss) if per_trade_loss else 0
    trades_until_max = int(max_limit // per_trade_loss) if per_trade_loss else 0
    be = 100.0 / (100.0 + payout_pct) * 100.0 if payout_pct > 0 else None
    return {
        "balance": balance,
        "daily_loss_limit": round(daily_limit, 2),
        "max_loss_limit": round(max_limit, 2),
        "stake_per_trade": round(stake, 2),
        "trades_until_daily_limit": trades_until_daily,
        "trades_until_max_limit": trades_until_max,
        "break_even_win_rate": round(be, 2) if be else None,
        "current_win_rate": win_rate_pct,
        "compliant": (be is None or win_rate_pct > be),
        "warning": ("Sua taxa atual esta abaixo do ponto de equilibrio do "
                    "payout: o sistema perde dinheiro no longo prazo."
                    if be and win_rate_pct <= be else
                    "Taxa atual acima do ponto de equilibrio."),
    }
