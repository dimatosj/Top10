import json
import os
import sys
import instaloader


def save_post_data(post_dir, video_bytes, caption, metadata):
    os.makedirs(post_dir, exist_ok=True)
    with open(os.path.join(post_dir, "video.mp4"), "wb") as f:
        f.write(video_bytes)
    with open(os.path.join(post_dir, "caption.txt"), "w") as f:
        f.write(caption or "")
    with open(os.path.join(post_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)


def download_saved(username, data_dir):
    posts_dir = os.path.join(data_dir, "posts")
    os.makedirs(posts_dir, exist_ok=True)

    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )

    try:
        L.load_session_from_file(username)
        print(f"Loaded existing session for {username}")
    except FileNotFoundError:
        print(f"No saved session found. Logging in as {username}...")
        L.interactive_login(username)
        print("Login successful.")

    profile = instaloader.Profile.from_username(L.context, username)

    processed = 0
    skipped = 0
    failed = 0

    print("Fetching saved posts...")
    for post in profile.get_saved_posts():
        shortcode = post.shortcode
        post_dir = os.path.join(posts_dir, shortcode)

        if os.path.exists(post_dir):
            skipped += 1
            continue

        if not post.is_video:
            if post.typename == "GraphSidecar":
                has_video = False
                for node in post.get_sidecar_nodes():
                    if node.is_video:
                        has_video = True
                        break
                if not has_video:
                    skipped += 1
                    continue
            else:
                skipped += 1
                continue

        try:
            if post.typename == "GraphSidecar":
                for node in post.get_sidecar_nodes():
                    if node.is_video:
                        video_url = node.video_url
                        break
            else:
                video_url = post.video_url

            video_path = os.path.join(post_dir, "video.mp4")
            os.makedirs(post_dir, exist_ok=True)
            L.context.get_and_write_raw(video_url, video_path)

            metadata = {
                "shortcode": shortcode,
                "timestamp": post.date_utc.isoformat(),
                "owner": post.owner_username,
                "url": f"https://www.instagram.com/p/{shortcode}/",
            }
            with open(os.path.join(post_dir, "caption.txt"), "w") as f:
                f.write(post.caption or "")
            with open(os.path.join(post_dir, "metadata.json"), "w") as f:
                json.dump(metadata, f, indent=2)
            processed += 1
            print(f"  Downloaded {shortcode} ({processed} so far)")
        except Exception as e:
            failed += 1
            print(f"  Failed {shortcode}: {e}")

    print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Failed: {failed}")
