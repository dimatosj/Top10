import json
import os
import pytest
from fb_downloader import parse_export


def test_parse_export_extracts_video_urls(tmp_path):
    export_dir = tmp_path / "your_facebook_activity" / "saves_and_collections"
    export_dir.mkdir(parents=True)
    (export_dir / "saves_and_collections_v2.json").write_text(json.dumps({
        "saves_and_collections_v2": [
            {
                "timestamp": 1714000000,
                "title": "Cool music video",
                "data": [{"text": "Check out this album review"}],
                "attachments": [{"data": [{"external_context": {"url": "https://www.facebook.com/watch/?v=123456789"}}]}],
            },
            {
                "timestamp": 1714100000,
                "title": "Another video",
                "data": [{"text": "More music"}],
                "attachments": [{"data": [{"external_context": {"url": "https://fb.watch/abc123"}}]}],
            },
        ]
    }))

    entries = parse_export(str(tmp_path))
    assert len(entries) == 2
    assert entries[0]["url"] == "https://www.facebook.com/watch/?v=123456789"
    assert entries[0]["video_id"] == "fb_123456789"
    assert entries[0]["timestamp"] == 1714000000
    assert entries[0]["caption"] == "Check out this album review"
    assert entries[1]["url"] == "https://fb.watch/abc123"
    assert entries[1]["video_id"] == "fb_abc123"


def test_parse_export_skips_non_video_urls(tmp_path):
    export_dir = tmp_path / "your_facebook_activity" / "saves_and_collections"
    export_dir.mkdir(parents=True)
    (export_dir / "saves_and_collections_v2.json").write_text(json.dumps({
        "saves_and_collections_v2": [
            {
                "timestamp": 1714000000,
                "title": "A photo post",
                "data": [{"text": "Nice photo"}],
                "attachments": [{"data": [{"external_context": {"url": "https://www.facebook.com/photo/?fbid=999"}}]}],
            },
            {
                "timestamp": 1714000000,
                "title": "No attachments",
                "data": [{"text": "Just text"}],
            },
            {
                "timestamp": 1714000000,
                "title": "Empty attachments",
                "data": [],
                "attachments": [],
            },
        ]
    }))

    entries = parse_export(str(tmp_path))
    assert len(entries) == 0
