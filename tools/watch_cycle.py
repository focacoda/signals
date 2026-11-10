"""Observa o ciclo medir -> alertar -> abrir e imprime so as transicoes.

Uso: python tools/watch_cycle.py [segundos]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.load(r)


def main() -> None:
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    end = time.time() + duration
    prev_phase: dict[str, str] = {}
    seen_alerts: set[str] = set()
    last_signal_id = 0

    # estado inicial
    try:
        snap = get("/api/snapshot")
        for k, v in snap["assessments"].items():
            prev_phase[k] = v.get("phase", "?")
        sigs = get("/api/signals?limit=1")["signals"]
        if sigs:
            last_signal_id = sigs[0]["id"]
    except Exception as exc:
        print("erro inicial:", exc, flush=True)

    while time.time() < end:
        try:
            snap = get("/api/snapshot")
            now = time.strftime("%H:%M:%S")

            counts: dict[str, int] = {}
            for k, v in snap["assessments"].items():
                ph = v.get("phase", "?")
                counts[ph] = counts.get(ph, 0) + 1
                if prev_phase.get(k) != ph:
                    prev_phase[k] = ph
                    if ph in ("medindo", "alerta"):
                        print(f"{now} FASE {k} -> {ph} "
                              f"conf={v['confidence']} "
                              f"fecha em {v['seconds_to_close']:.0f}s",
                              flush=True)

            for k, a in snap.get("alerts", {}).items():
                if k not in seen_alerts:
                    seen_alerts.add(k)
                    print(f"{now} ALERTA {k} {a['direction']} "
                          f"conf={a['confidence']} "
                          f"abre em {a['seconds_to_open']:.0f}s", flush=True)

            sigs = get("/api/signals?limit=3")["signals"]
            for s in reversed(sigs):
                if s["id"] > last_signal_id:
                    last_signal_id = s["id"]
                    print(f"{now} SINAL #{s['id']} {s['symbol']} "
                          f"M{s['expiry_min']} {s['direction']} "
                          f"conf={s['confidence']} "
                          f"abre={time.strftime('%H:%M', time.localtime(s['opened_at']))} "
                          f"fecha={time.strftime('%H:%M', time.localtime(s['expires_at']))}",
                          flush=True)
        except Exception:
            pass
        time.sleep(2)


if __name__ == "__main__":
    main()
