import asyncio,sys
sys.path.insert(0,".")
from app.feeds.iq import IQFeed
from app.feeds.base import ASSETS
f=IQFeed()
a=[x for x in ASSETS if x.symbol=="EURUSD"][0]
print(asyncio.run(f.candles(a,5))[:2])
