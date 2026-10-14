import os
import re

from .common import hashtags, log

NAME = "youtube"


def enabled():
    return all(os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def publish(video_path, meta):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    title = meta["title"].strip()[:90]
    if "#shorts" not in title.lower():
        title = f"{title} #shorts"
    tags = [t.strip()[:30] for t in meta.get("tags", []) if t.strip()][:12]
    description = f"{meta.get('description', '').strip()}\n\n{hashtags(meta, 3)} #shorts"
    if meta.get("footage_credit"):
        description += f"\n\nFootage: {meta['footage_credit']}"
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags, "categoryId": "27"},
        "status": {
            "privacyStatus": os.environ.get("PRIVACY_STATUS") or "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }
    log(NAME, "uploading")
    req = yt.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4"),
    )
    response = None
    while response is None:
        _, response = req.next_chunk()
    return f"https://youtube.com/shorts/{response['id']}"
