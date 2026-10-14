import os
from pathlib import Path

import requests

from .common import GRAPH_BASE, GRAPH_VERSION, check, log, social_caption, wait_until

NAME = "facebook"


def enabled():
    return bool(os.environ.get("FB_PAGE_ID") and os.environ.get("META_PAGE_TOKEN"))


def publish(video_path, meta):
    page = os.environ["FB_PAGE_ID"]
    token = os.environ["META_PAGE_TOKEN"]
    api = f"{GRAPH_BASE}/{GRAPH_VERSION}"
    size = Path(video_path).stat().st_size

    start = check(
        requests.post(f"{api}/{page}/video_reels", data={"upload_phase": "start", "access_token": token}, timeout=60),
        NAME, "start upload session",
    )
    video_id = start["video_id"]
    upload_url = start.get("upload_url") or f"https://rupload.facebook.com/video-upload/{GRAPH_VERSION}/{video_id}"

    with open(video_path, "rb") as f:
        check(
            requests.post(upload_url, headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
                          data=f, timeout=600),
            NAME, f"upload {size // 1024} KB",
        )

    check(
        requests.post(f"{api}/{page}/video_reels", data={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": social_caption(meta),
            "access_token": token,
        }, timeout=60),
        NAME, "publish",
    )

    def ready():
        r = requests.get(f"{api}/{video_id}", params={"fields": "status", "access_token": token}, timeout=30)
        status = check(r, NAME, "status check").get("status", {})
        for phase in ("uploading_phase", "processing_phase", "publishing_phase"):
            if status.get(phase, {}).get("status") == "error":
                raise RuntimeError(f"{phase} error: {status[phase].get('errors')}")
        return status.get("video_status") == "ready" or status.get("publishing_phase", {}).get("status") == "complete"

    wait_until(ready, NAME, "processing")
    return f"https://www.facebook.com/reel/{video_id}"
