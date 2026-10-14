import asyncio
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
HISTORY_FILE = ROOT / "data" / "history.json"

NICHE = os.environ.get("NICHE") or "surprising science and nature facts"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-3.8-flash"
VOICE = os.environ.get("TTS_VOICE") or "en-US-AndrewNeural"
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

W, H = 1080, 1920


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []


def save_history(history):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def generate_script(history):
    key = os.environ["GEMINI_API_KEY"]
    recent = [h["title"] for h in history[-60:]]
    prompt = f"""You write scripts for a YouTube Shorts channel about {NICHE}.
Write ONE new short. Requirements:
- A single, specific, true and verifiable fact or story. No made-up claims, no exaggeration.
- Spoken script of 110-140 words. First sentence is a strong hook. End with a short line that invites a comment.
- Plain spoken English, no emojis, no hashtags, no stage directions inside the script.
- Do NOT repeat any of these previous topics: {json.dumps(recent, ensure_ascii=False)}

Return ONLY JSON with these keys:
"title": catchy title under 70 characters,
"script": the spoken script,
"visual_keywords": list of 4 short stock-footage search terms (2-3 words each) that match the script in order,
"description": 2-3 sentence YouTube description,
"tags": list of 8 short tags"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 1.0, "responseMimeType": "application/json"},
    }
    for attempt in range(3):
        r = requests.post(url, params={"key": key}, json=body, timeout=90)
        if r.status_code == 200:
            parts = r.json()["candidates"][0]["content"].get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
            try:
                data = json.loads(text)
            except ValueError:
                log(f"Gemini attempt {attempt + 1} returned non-JSON: {text[:200]}")
                continue
            if data.get("title") and data.get("script"):
                return data
            log(f"Gemini attempt {attempt + 1} missing title or script")
            continue
        log(f"Gemini attempt {attempt + 1} failed: {r.status_code} {r.text[:300]}")
    raise RuntimeError("Could not generate script")


async def _tts(text, mp3_path):
    import edge_tts

    words = []
    communicate = edge_tts.Communicate(text, VOICE, rate="+8%", boundary="WordBoundary")
    with open(mp3_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append(
                    {
                        "word": chunk["text"],
                        "start": chunk["offset"] / 1e7,
                        "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                    }
                )
    return words


def text_to_speech(text, mp3_path):
    return asyncio.run(_tts(text, mp3_path))


def media_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def download(url, dest):
    with requests.get(url, stream=True, timeout=120) as dl:
        dl.raise_for_status()
        with open(dest, "wb") as out:
            for part in dl.iter_content(1 << 20):
                out.write(part)


def pixabay_clips(kw, key):
    r = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": key, "q": kw[:100], "safesearch": "true", "per_page": 15, "video_type": "film"},
        timeout=30,
    )
    r.raise_for_status()
    found = []
    for hit in r.json().get("hits", []):
        if hit.get("duration", 0) < 4:
            continue
        renditions = [v for v in hit["videos"].values() if v.get("url") and v.get("height", 0) >= 720]
        if not renditions:
            continue
        portrait = [v for v in renditions if v["height"] > v["width"]]
        pool = portrait or renditions
        best = min(pool, key=lambda v: abs(max(v["width"], v["height"]) - 1920))
        found.append((f"pixabay-{hit['id']}", best["url"], bool(portrait)))
    found.sort(key=lambda c: not c[2])
    return [(cid, url) for cid, url, _ in found]


def pexels_clips(kw, key):
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": key},
        params={"query": kw, "orientation": "portrait", "per_page": 8, "size": "medium"},
        timeout=30,
    )
    r.raise_for_status()
    found = []
    for v in r.json().get("videos", []):
        files = [f for f in v["video_files"] if f.get("height") and f["height"] >= 1280 and f.get("file_type") == "video/mp4"]
        if files:
            best = min(files, key=lambda f: abs(f["height"] - 1920))
            found.append((f"pexels-{v['id']}", best["link"]))
    random.shuffle(found)
    return found


def fetch_footage(keywords, workdir, count_needed):
    sources = []
    if os.environ.get("PIXABAY_API_KEY"):
        sources.append(("Pixabay", pixabay_clips, os.environ["PIXABAY_API_KEY"]))
    if os.environ.get("PEXELS_API_KEY"):
        sources.append(("Pexels", pexels_clips, os.environ["PEXELS_API_KEY"]))
    clips, credits, used = [], set(), set()
    if not sources:
        log("No footage API key set, using plain background")
        return clips, credits
    for kw in keywords:
        for name, search, key in sources:
            try:
                candidates = [c for c in search(kw, key) if c[0] not in used][:3]
                taken = 0
                for cid, url in candidates:
                    if taken == 2:
                        break
                    dest = workdir / f"clip_{len(clips)}.mp4"
                    try:
                        download(url, dest)
                    except Exception as e:
                        log(f"Download failed for {cid}: {e}")
                        continue
                    used.add(cid)
                    clips.append(dest)
                    credits.add(name)
                    taken += 1
                    log(f"Downloaded {cid} for '{kw}'")
                if taken:
                    break
            except Exception as e:
                log(f"{name} search failed for '{kw}': {e}")
        if len(clips) >= count_needed:
            break
    return clips, credits


def ass_time(t):
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_captions(words, ass_path, total):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,7,3,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    groups = [words[i:i + 3] for i in range(0, len(words), 3)]
    for gi, g in enumerate(groups):
        start = g[0]["start"]
        end = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else min(total, g[-1]["end"] + 0.4)
        text = " ".join(w["word"] for w in g).upper().replace("{", "").replace("}", "")
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,{{\\fad(60,0)}}{text}")
    Path(ass_path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def assemble(clips, audio, ass_path, out_path, workdir):
    total = media_duration(audio) + 0.5
    norm = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,setsar=1"
    segments = []
    if clips:
        seg_len = total / max(len(clips), 1)
        seg_len = max(seg_len, 3.0)
        n = int(total // seg_len) + 1
        for i in range(n):
            src = clips[i % len(clips)]
            seg = workdir / f"seg_{i}.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(src), "-t", f"{seg_len:.2f}",
                 "-vf", norm, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", str(seg)],
                check=True,
            )
            segments.append(seg)
    else:
        seg = workdir / "seg_0.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"gradients=s={W}x{H}:c0=0x1b2a49:c1=0x0f5e5a:speed=0.01:r=30", "-t", f"{total:.2f}",
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(seg)],
            check=True,
        )
        segments.append(seg)

    concat_list = workdir / "concat.txt"
    concat_list.write_text("".join(f"file '{s}'\n" for s in segments))
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-i", str(audio),
         "-vf", f"eq=brightness=-0.06,ass='{ass_escaped}'", "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out_path)],
        check=True,
    )
    log(f"Rendered {out_path} ({total:.1f}s)")


def publish_everywhere(video_path, meta):
    from publishers import ALL

    only = [p.strip().lower() for p in (os.environ.get("PLATFORMS") or "").split(",") if p.strip()]
    results = {}
    for name, module in ALL.items():
        if only and name not in only:
            continue
        if not module.enabled():
            log(f"{name}: skipped (no credentials set)")
            continue
        try:
            url = module.publish(video_path, meta)
            results[name] = {"status": "posted", "url": url}
            log(f"{name}: posted {url}")
        except Exception as e:
            results[name] = {"status": "failed", "error": str(e)[:500]}
            log(f"{name}: FAILED {e}")
    return results


def main():
    history = load_history()
    log(f"Niche: {NICHE} | previous videos: {len(history)}")
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        meta = generate_script(history)
        log(f"Script: {meta['title']}")
        audio = workdir / "voice.mp3"
        words = text_to_speech(meta["script"], audio)
        if not words:
            raise RuntimeError("TTS returned no word timings")
        log(f"Voiceover: {len(words)} words, {media_duration(audio):.1f}s")
        ass = workdir / "captions.ass"
        build_captions(words, ass, media_duration(audio) + 0.5)
        clips, credits = fetch_footage(meta.get("visual_keywords", [NICHE]), workdir, 6)
        meta["footage_credit"] = ", ".join(sorted(credits))
        out = ROOT / "output.mp4"
        assemble(clips, audio, ass, out, workdir)
        duration = media_duration(out)
        if duration > 59:
            raise RuntimeError("Video longer than a Short allows")

    if DRY_RUN:
        log("Dry run: rendered output.mp4, nothing published")
        return True

    results = publish_everywhere(out, meta)
    history.append({
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": meta["title"],
        "duration": round(duration, 1),
        "platforms": results,
    })
    save_history(history)
    failed = [n for n, r in results.items() if r["status"] == "failed"]
    if not results:
        log("No platforms configured, nothing was published")
        return False
    if failed:
        log(f"Finished with failures on: {', '.join(failed)}")
        return False
    log("Done")
    return True


if __name__ == "__main__":
    try:
        ok = main()
    except Exception as e:
        log(f"FAILED: {e}")
        ok = False
    sys.exit(0 if ok else 1)