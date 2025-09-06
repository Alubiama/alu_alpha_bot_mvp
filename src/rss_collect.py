import asyncio, feedparser, requests
from datetime import datetime, timedelta, timezone

HEADERS = {"User-Agent": "ALU-AlphaBot/0.1"}

def fetch_rss(url: str, timeout: int = 12):
    r = requests.get(url, headers=HEADERS, timeout=timeout); r.raise_for_status()
    feed = feedparser.parse(r.text); out = []
    for e in feed.entries:
        dt = None
        for k in ("published_parsed","updated_parsed"):
            val = getattr(e, k, None)
            if val: dt = datetime(*val[:6], tzinfo=timezone.utc); break
        out.append({"title": getattr(e,"title",""),
                    "summary": getattr(e,"summary",""),
                    "link": getattr(e,"link",""),
                    "dt": dt})
    return out

async def fetch_rss_batch(urls, timeout: int = 12, lookback_hours: int = 48):
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, fetch_rss, u, timeout) for u in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    now = datetime.now(timezone.utc); items = []
    for r in results:
        if isinstance(r, Exception): continue
        for it in r:
            dt = it.get("dt")
            if dt is None or (now - dt) <= timedelta(hours=lookback_hours):
                items.append(it)
    return items
