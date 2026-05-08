import os
import subprocess
import sys


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ffmpeg is required but not found. Install it: brew install ffmpeg")
        sys.exit(1)


def extract_audio(video_path, audio_path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "4", audio_path],
        capture_output=True,
        check=True,
    )


def extract_all_audio(data_dir):
    check_ffmpeg()
    posts_dir = os.path.join(data_dir, "posts")
    if not os.path.exists(posts_dir):
        print("No posts directory found. Run 'download' first.")
        return {"processed": 0, "skipped": 0, "failed": 0}

    shortcodes = sorted(
        d for d in os.listdir(posts_dir)
        if os.path.isdir(os.path.join(posts_dir, d))
    )

    processed = 0
    skipped = 0
    failed = 0

    for i, shortcode in enumerate(shortcodes, 1):
        post_dir = os.path.join(posts_dir, shortcode)
        video_path = os.path.join(post_dir, "video.mp4")
        audio_path = os.path.join(post_dir, "audio.mp3")

        if os.path.exists(audio_path):
            skipped += 1
            continue

        if not os.path.exists(video_path):
            skipped += 1
            continue

        try:
            extract_audio(video_path, audio_path)
            processed += 1
            print(f"  Extracted audio {i}/{len(shortcodes)}: {shortcode}")
        except subprocess.CalledProcessError as e:
            failed += 1
            print(f"  Failed {shortcode}: {e.stderr.decode() if e.stderr else e}")

    print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Failed: {failed}")
    return {"processed": processed, "skipped": skipped, "failed": failed}
