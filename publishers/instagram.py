import os
from pathlib import Path

import requests

from .common import GRAPH_BASE, GRAPH_VERSION, check, log, social_caption, wait_until

NAME = "instagram"


def enabled():
    return bool(os.environ.get("IG_USER_ID") and os.environ.get("META_PAGE_TOKEN"))


def publish(video_path, meta):
    ig = os.environ["IG_USER_ID"]
    token = os.environ["META_PAGE_TOKEN"]
    api = f"{GRAPH_BASE}/{GRAPH_VERSION}"
    size = Path(video_path).stat().st_size

    container = check(
        requests.post(f"{api}/{ig}/media", data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": social_caption(meta),
            "share_to_feed": "true",
            "access_token": token,
        }, timeout=60),
        NAME, "create container",
    )
    cid = container["id"]
    upload_url = container.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}/{cid}"

    with open(video_path, "rb") as f:
        check(
            requests.post(upload_url, headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
                          data=f, timeout=600),
            NAME, f"upload {size // 1024} KB",
        )

    def finished():
        r = requests.get(f"{api}/{cid}", params={"fields": "status_code,status", "access_token": token}, timeout=30)
        data = check(r, NAME, "status check")
        code = data.get("status_code")
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing {code}: {data.get('status')}")
        return code == "FINISHED"

    wait_until(finished, NAME, "processing")

    media = check(
        requests.post(f"{api}/{ig}/media_publish", data={"creation_id": cid, "access_token": token}, timeout=60),
        NAME, "publish",
    )
    r = requests.get(f"{api}/{media['id']}", params={"fields": "permalink", "access_token": token}, timeout=30)
    link = r.json().get("permalink") if r.ok else None
    log(NAME, f"media id {media['id']}")
    return link or f"https://www.instagram.com/"
