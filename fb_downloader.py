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


def _parse_old_format(json_path):
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


def _extract_saved_poster_names(saves_path):
    with open(saves_path) as f:
        data = json.load(f)

    names = set()
    for item in data.get("saves_v2", []):
        title = item.get("title", "").replace("’", "'")
        match = re.search(r"saved (?:a reel from )?(.+)'s post\.", title)
        if match:
            names.add(match.group(1).lower())
    return names


def _parse_watched_videos(viewed_path, saved_names=None):
    with open(viewed_path) as f:
        data = json.load(f)

    videos_section = None
    for section in data.get("recently_viewed", []):
        if "Videos" in section.get("name", ""):
            videos_section = section
            break

    if not videos_section:
        return []

    seen_urls = set()
    entries = []
    for entry in videos_section.get("entries", []):
        uri = entry.get("data", {}).get("uri", "")
        name = entry.get("data", {}).get("name", "")

        if not uri or not is_video_url(uri):
            continue
        if uri in seen_urls:
            continue

        if saved_names is not None:
            poster = re.sub(r"'s video$", "", name.replace("’", "'")).lower()
            if poster not in saved_names:
                continue

        seen_urls.add(uri)
        entries.append({
            "url": uri,
            "video_id": extract_video_id(uri),
            "timestamp": entry.get("timestamp", 0),
            "title": name,
            "caption": "",
        })

    return entries


def parse_export(export_path):
    old_path = os.path.join(
        export_path, "your_facebook_activity",
        "saves_and_collections", "saves_and_collections_v2.json",
    )
    if os.path.exists(old_path):
        return _parse_old_format(old_path)

    viewed_path = os.path.join(
        export_path, "logged_information",
        "interactions", "recently_viewed.json",
    )
    if not os.path.exists(viewed_path):
        print(f"No saved items or watched videos found in export at {export_path}")
        return []

    saves_path = os.path.join(
        export_path, "your_facebook_activity",
        "saved_items_and_collections", "your_saved_items.json",
    )
    saved_names = None
    if os.path.exists(saves_path):
        saved_names = _extract_saved_poster_names(saves_path)
        if saved_names:
            print(f"Cross-referencing {len(saved_names)} saved posters with watched videos...")

    entries = _parse_watched_videos(viewed_path, saved_names)

    if not entries and saved_names:
        print("No matches after filtering. Using all watched videos.")
        entries = _parse_watched_videos(viewed_path, saved_names=None)

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


def download_facebook_saved(export_path, data_dir, browser="chrome"):
    check_ytdlp()
    posts_dir = os.path.join(data_dir, "posts")
    os.makedirs(posts_dir, exist_ok=True)

    entries = parse_export(export_path)
    if not entries:
        print("No video entries found in Facebook export.")
        return {"processed": 0, "skipped": 0, "failed": 0}

    processed = 0
    skipped = 0
    failed = 0

    print(f"Found {len(entries)} video entries in Facebook export.")

    for i, entry in enumerate(entries, 1):
        video_id = entry["video_id"]
        post_dir = os.path.join(posts_dir, video_id)

        if os.path.exists(post_dir):
            skipped += 1
            continue

        os.makedirs(post_dir, exist_ok=True)
        video_path = os.path.join(post_dir, "video.mp4")

        try:
            download_video(entry["url"], video_path, browser=browser)

            timestamp = datetime.fromtimestamp(entry["timestamp"], tz=timezone.utc).isoformat()
            metadata = {
                "shortcode": video_id,
                "timestamp": timestamp,
                "owner": "facebook",
                "url": entry["url"],
                "source": "facebook",
            }

            with open(os.path.join(post_dir, "caption.txt"), "w") as f:
                f.write(entry["caption"])
            with open(os.path.join(post_dir, "metadata.json"), "w") as f:
                json.dump(metadata, f, indent=2)

            processed += 1
            print(f"  Downloaded {i}/{len(entries)}: {video_id}")
        except subprocess.CalledProcessError as e:
            failed += 1
            shutil.rmtree(post_dir, ignore_errors=True)
            print(f"  Failed {video_id}: {e.stderr.decode() if e.stderr else e}")
        except Exception as e:
            failed += 1
            print(f"  Failed {video_id}: {e}")

    print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Failed: {failed}")
    return {"processed": processed, "skipped": skipped, "failed": failed}
