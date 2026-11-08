import json
from pathlib import Path

d = json.loads(Path("data/iq_debug.json").read_text(encoding="utf-8"))
for e in d:
    if e["name"] == "candles":
        print("CANDLES:", json.dumps(e["msg"], ensure_ascii=False)[:800])
