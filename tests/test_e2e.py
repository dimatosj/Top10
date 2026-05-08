import json
import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from extractor import extract_all_audio
from spotify_client import create_playlists
from config import Config


@pytest.fixture
def populated_data_dir(tmp_path):
    """Set up a data dir with a fake downloaded post."""
    posts_dir = tmp_path / "posts" / "SMOKE01"
    posts_dir.mkdir(parents=True)

    # Create a minimal video with audio
    video_path = str(posts_dir / "video.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=1",
            "-f", "lavfi", "-i",
            "color=c=black:s=320x240:d=1",
            "-shortest", video_path,
        ],
        capture_output=True,
        check=True,
    )

    (posts_dir / "caption.txt").write_text("Top 3 albums: Kid A by Radiohead")
    (posts_dir / "metadata.json").write_text(json.dumps({
        "shortcode": "SMOKE01",
        "timestamp": "2026-03-10T12:00:00",
        "owner": "musiclover",
        "url": "https://www.instagram.com/p/SMOKE01/",
    }))

    return str(tmp_path)


def test_extract_produces_audio(populated_data_dir):
    stats = extract_all_audio(data_dir=populated_data_dir)
    assert stats["processed"] == 1
    audio_path = os.path.join(populated_data_dir, "posts", "SMOKE01", "audio.mp3")
    assert os.path.exists(audio_path)


def test_playlist_skips_when_no_analysis(populated_data_dir):
    cfg = Config(
        spotify_client_id="id",
        spotify_client_secret="secret",
        spotify_redirect_uri="http://localhost:8888/callback",
    )
    with patch("spotify_client.get_spotify_client") as mock_get:
        stats = create_playlists(config=cfg, data_dir=populated_data_dir)
        assert stats["processed"] == 0


def test_playlist_creates_from_analysis(populated_data_dir):
    analysis_dir = os.path.join(populated_data_dir, "analysis")
    os.makedirs(analysis_dir)

    with open(os.path.join(analysis_dir, "SMOKE01.json"), "w") as f:
        json.dump({
            "transcript": "check out Kid A by Radiohead",
            "albums": [{"artist": "Radiohead", "album": "Kid A"}],
            "has_music": True,
        }, f)

    mock_sp = MagicMock()
    mock_sp.current_user.return_value = {"id": "testuser"}
    mock_sp.user_playlist_create.return_value = {
        "id": "pl_123",
        "external_urls": {"spotify": "https://open.spotify.com/playlist/pl_123"},
    }
    mock_sp.search.return_value = {
        "albums": {"items": [{"id": "album_abc", "name": "Kid A"}]}
    }
    mock_sp.album_tracks.return_value = {
        "items": [
            {"uri": "spotify:track:1"},
            {"uri": "spotify:track:2"},
        ],
        "next": None,
    }

    cfg = Config(
        spotify_client_id="id",
        spotify_client_secret="secret",
        spotify_redirect_uri="http://localhost:8888/callback",
    )

    with patch("spotify_client.get_spotify_client", return_value=mock_sp):
        stats = create_playlists(config=cfg, data_dir=populated_data_dir)

    assert stats["processed"] == 1
    playlist_file = os.path.join(populated_data_dir, "playlists", "SMOKE01.json")
    assert os.path.exists(playlist_file)
    with open(playlist_file) as f:
        result = json.load(f)
    assert result["playlist_id"] == "pl_123"
    assert len(result["albums_added"]) == 1
    assert result["albums_added"][0]["artist"] == "Radiohead"
