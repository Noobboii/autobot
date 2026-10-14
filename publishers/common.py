import os
import re
import time
from datetime import datetime, timezone

GRAPH_VERSION = os.environ.get("GRAPH_VERSION") or "v24.0"
GRAPH_BASE = (os.environ.get("GRAPH_BASE") or "https://graph.facebook.com").rstrip("/")


def log(platform, msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [{platform}] {msg}", flush=True)


def hashtags(meta, limit):
    tags = []
    for t in meta.get("tags", []):
        clean = re.sub(r"\W", "", t)
        if clean and clean.lower() not in (x.lower() for x in tags):
            tags.append(clean)
    return " ".join("#" + t for t in tags[:limit])


def social_caption(meta, limit=2200):
    text = f"{meta['title'].strip()}\n\n{meta.get('description', '').strip()}\n\n{hashtags(meta, 8)}"
    return text[:limit]


def check(resp, platform, step):
    if resp.status_code >= 400:
        raise RuntimeError(f"{step} failed ({resp.status_code}): {resp.text[:400]}")
    log(platform, f"{step} ok")
    try:
        return resp.json()
    except ValueError:
        return {}


def wait_until(fn, platform, what, timeout=600, every=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        done = fn()
        if done:
            return done
        log(platform, f"waiting for {what}...")
        time.sleep(every)
    raise RuntimeError(f"Timed out waiting for {what}")
