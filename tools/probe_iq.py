"""Sonda os endpoints da IQ Option: o conector atual vs candidatos do bundle.

Nao envia credenciais. So verifica: o host resolve? responde HTTP? o
websocket aceita handshake? Serve para saber se o conector esta apontando
para um host morto antes de culpar a autenticacao.
"""
from __future__ import annotations

import asyncio
import socket
import ssl

import httpx
import websockets


def dns(host: str) -> str:
    try:
        return socket.gethostbyname(host)
    except Exception as e:
        return f"FALHA ({type(e).__name__})"


async def http_probe(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=12.0, verify=False) as c:
            r = await c.get(url)
            return f"HTTP {r.status_code} ({len(r.content)} bytes)"
    except Exception as e:
        return f"ERRO {type(e).__name__}"


async def ws_probe(url: str) -> str:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        async with websockets.connect(url, ssl=ctx, open_timeout=12,
                                      close_timeout=3) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=8)
                return f"CONECTOU, 1a msg: {str(msg)[:120]}"
            except asyncio.TimeoutError:
                return "CONECTOU (nenhuma msg em 8s)"
    except Exception as e:
        return f"ERRO {type(e).__name__}: {str(e)[:90]}"


async def main() -> None:
    print("=" * 72)
    print(" DNS")
    print("=" * 72)
    for h in ["api-iqoption.com", "api.eu.iqoption.com",
              "auth.iqoption.com", "iqoption.com", "ws.iqoption.com"]:
        print(f"  {h:26} -> {dns(h)}")

    print()
    print("=" * 72)
    print(" HTTP (endpoints de login/config)")
    print("=" * 72)
    for url in [
        "https://auth.iqoption.com/api/v2/login",
        "https://api.eu.iqoption.com/api/v2/login",
        "https://api.eu.iqoption.com/api/getconfiguration",
        "https://api.eu.iqoption.com/api/v1.0/get-config",
    ]:
        print(f"  {url:50} {await http_probe(url)}")

    print()
    print("=" * 72)
    print(" WEBSOCKET (handshake)")
    print("=" * 72)
    for url in [
        "wss://api-iqoption.com/echo/websocket",
        "wss://api.eu.iqoption.com/echo/websocket",
        "wss://ws.iqoption.com/echo/websocket",
        "wss://api.eu.iqoption.com/echo",
    ]:
        print(f"  {url:50} {await ws_probe(url)}")


if __name__ == "__main__":
    asyncio.run(main())
