import json
import os


def load_post_metadata(posts_dir, shortcode):
    metadata_path = os.path.join(posts_dir, shortcode, "metadata.json")
    caption_path = os.path.join(posts_dir, shortcode, "caption.txt")
    owner = shortcode
    caption = ""
    if os.path.exists(metadata_path):
        with open(metadata_path) as f:
            meta = json.load(f)
        owner = meta.get("owner", shortcode)
    if os.path.exists(caption_path):
        with open(caption_path) as f:
            caption = f.read()
    return owner, caption
