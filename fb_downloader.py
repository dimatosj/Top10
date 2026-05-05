import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone


VIDEO_URL_PATTERNS = [
    r"facebook\.com/watch",
    r"facebook\.com/.*/videos/",
    r"fb\.watch/",
    r"facebook\.com/reel/",
]


def is_video_url(url):
    return any(re.search(pattern, url) for pattern in VIDEO_URL_PATTERNS)


def extract_video_id(url):
    match = re.search(r"[?&]v=(\d+)", url)
    if match:
        return f"fb_{match.group(1)}"
    match = re.search(r"/videos/(\d+)", url)
    if match:
        return f"fb_{match.group(1)}"
    match = re.search(r"/reel/(\d+)", url)
    if match:
        return f"fb_{match.group(1)}"
    match = re.search(r"fb\.watch/([^/?]+)", url)
    if match:
        return f"fb_{match.group(1)}"
    return f"fb_{abs(hash(url))}"


def parse_export(export_path):
    json_path = os.path.join(
        export_path,
        "your_facebook_activity",
        "saves_and_collections",
        "saves_and_collections_v2.json",
    )
    with open(json_path) as f:
        data = json.load(f)

    entries = []
    for item in data.get("saves_and_collections_v2", []):
        attachments = item.get("attachments", [])
        if not attachments:
            continue
        attach_data = attachments[0].get("data", [])
        if not attach_data:
            continue
        external = attach_data[0].get("external_context", {})
        url = external.get("url", "")
        if not url or not is_video_url(url):
            continue

        item_data = item.get("data", [])
        caption = item_data[0].get("text", "") if item_data else ""

        entries.append({
            "url": url,
            "video_id": extract_video_id(url),
            "timestamp": item.get("timestamp", 0),
            "title": item.get("title", ""),
            "caption": caption,
        })

    return entries


def check_ytdlp():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("yt-dlp is required but not found. Install it: brew install yt-dlp")
        sys.exit(1)


def download_video(url, output_path, browser="chrome"):
    subprocess.run(
        ["yt-dlp", "--cookies-from-browser", browser, "-o", output_path, url],
        capture_output=True,
        check=True,
    )
