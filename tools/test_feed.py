import asyncio
import sys

sys.path.insert(0, ".")

from app.feeds.iq import IQFeed


async def main():
    f = IQFeed()
    cs = await f.candles("EURUSD", 5)
    print("status:", f.status())
    print("velas:", len(cs))
    for c in cs:
        print(c)
    await f.close()


if __name__ == "__main__":
    asyncio.run(main())
