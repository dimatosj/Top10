import json
import os
import pytest
from downloader import save_post_data


def test_save_post_data_writes_files(tmp_path):
    post_dir = tmp_path / "posts" / "ABC123"
    save_post_data(
        post_dir=str(post_dir),
        video_bytes=b"fake video content",
        caption="Check out this album",
        metadata={
            "shortcode": "ABC123",
            "timestamp": "2026-01-15T10:30:00",
            "owner": "musicfan",
            "url": "https://www.instagram.com/p/ABC123/",
        },
    )
    assert (post_dir / "video.mp4").read_bytes() == b"fake video content"
    assert (post_dir / "caption.txt").read_text() == "Check out this album"
    meta = json.loads((post_dir / "metadata.json").read_text())
    assert meta["shortcode"] == "ABC123"
    assert meta["owner"] == "musicfan"


def test_save_post_data_empty_caption(tmp_path):
    post_dir = tmp_path / "posts" / "DEF456"
    save_post_data(
        post_dir=str(post_dir),
        video_bytes=b"video",
        caption=None,
        metadata={"shortcode": "DEF456", "timestamp": "", "owner": "", "url": ""},
    )
    assert (post_dir / "caption.txt").read_text() == ""
