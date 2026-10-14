import os
import time
from pathlib import Path

import requests

from .common import check, hashtags, log, wait_until

NAME = "x"
KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")
X_BASE = (os.environ.get("X_API_BASE") or "https://api.x.com").rstrip("/")
CHUNK = 4 * 1024 * 1024


def enabled():
    return all(os.environ.get(k) for k in KEYS)


def publish(video_path, meta):
    from requests_oauthlib import OAuth1

    auth = OAuth1(*(os.environ[k] for k in KEYS))
    size = Path(video_path).stat().st_size

    init = check(
        requests.post(f"{X_BASE}/2/media/upload/initialize", auth=auth, timeout=60,
                      json={"media_type": "video/mp4", "total_bytes": size, "media_category": "tweet_video"}),
        NAME, "initialize upload",
    )
    media_id = init["data"]["id"]

    with open(video_path, "rb") as f:
        index = 0
        while chunk := f.read(CHUNK):
            check(
                requests.post(f"{X_BASE}/2/media/upload/{media_id}/append", auth=auth, timeout=300,
                              data={"segment_index": index}, files={"media": ("chunk", chunk, "application/octet-stream")}),
                NAME, f"append chunk {index}",
            )
            index += 1

    final = check(requests.post(f"{X_BASE}/2/media/upload/{media_id}/finalize", auth=auth, timeout=60), NAME, "finalize")
    info = final.get("data", {}).get("processing_info")

    if info:
        def processed():
            r = requests.get(f"{X_BASE}/2/media/upload", auth=auth, timeout=30,
                             params={"command": "STATUS", "media_id": media_id})
            state = check(r, NAME, "status check").get("data", {}).get("processing_info", {})
            if state.get("state") == "failed":
                raise RuntimeError(f"X processing failed: {state.get('error')}")
            if state.get("state") == "succeeded":
                return True
            time.sleep(max(0, state.get("check_after_secs", 5) - 5))
            return False

        wait_until(processed, NAME, "processing", every=5)

    text = f"{meta['title'].strip()}\n\n{hashtags(meta, 3)}"[:270]
    post = check(
        requests.post(f"{X_BASE}/2/tweets", auth=auth, timeout=60,
                      json={"text": text, "media": {"media_ids": [str(media_id)]}}),
        NAME, "create post",
    )
    return f"https://x.com/i/status/{post['data']['id']}"
