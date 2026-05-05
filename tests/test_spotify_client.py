import json
import os
import pytest
from unittest.mock import MagicMock, patch, call
from spotify_client import build_search_query, add_tracks_batched, create_playlists


def test_build_search_query():
    assert build_search_query("Radiohead", "Kid A") == "album:Kid A artist:Radiohead"


def test_build_search_query_special_characters():
    assert build_search_query("Guns N' Roses", "Appetite for Destruction") == (
        "album:Appetite for Destruction artist:Guns N' Roses"
    )


def test_add_tracks_batched_single_batch():
    sp = MagicMock()
    uris = [f"spotify:track:{i}" for i in range(50)]
    add_tracks_batched(sp, "playlist_123", uris)
    sp.playlist_add_items.assert_called_once_with("playlist_123", uris)


def test_add_tracks_batched_multiple_batches():
    sp = MagicMock()
    uris = [f"spotify:track:{i}" for i in range(250)]
    add_tracks_batched(sp, "playlist_123", uris)
    assert sp.playlist_add_items.call_count == 3
    sp.playlist_add_items.assert_any_call("playlist_123", uris[:100])
    sp.playlist_add_items.assert_any_call("playlist_123", uris[100:200])
    sp.playlist_add_items.assert_any_call("playlist_123", uris[200:250])


def test_create_playlists_skips_no_albums(tmp_path):
    data_dir = str(tmp_path)
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    posts_dir = tmp_path / "posts" / "ABC123"
    posts_dir.mkdir(parents=True)

    (posts_dir / "metadata.json").write_text(json.dumps({
        "shortcode": "ABC123",
        "owner": "testuser",
        "timestamp": "2026-01-15T10:30:00",
        "url": "https://www.instagram.com/p/ABC123/",
    }))
    (posts_dir / "caption.txt").write_text("no music here")

    (analysis_dir / "ABC123.json").write_text(json.dumps({
        "transcript": "just a random video",
        "albums": [],
        "has_music": False,
    }))

    playlists_dir = tmp_path / "playlists"

    with patch("spotify_client.get_spotify_client"):
        from config import Config
        cfg = Config(
            spotify_client_id="id",
            spotify_client_secret="secret",
            spotify_redirect_uri="http://localhost:8888/callback",
        )
        stats = create_playlists(config=cfg, data_dir=data_dir)
        assert stats["skipped"] >= 1
        assert not (playlists_dir / "ABC123.json").exists()


def test_create_playlists_skips_existing_playlist(tmp_path):
    data_dir = str(tmp_path)
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    playlists_dir = tmp_path / "playlists"
    playlists_dir.mkdir()

    (analysis_dir / "XYZ789.json").write_text(json.dumps({
        "transcript": "check out Kid A by Radiohead",
        "albums": [{"artist": "Radiohead", "album": "Kid A"}],
        "has_music": True,
    }))
    (playlists_dir / "XYZ789.json").write_text(json.dumps({
        "playlist_id": "existing",
        "playlist_url": "https://open.spotify.com/playlist/existing",
        "albums_added": [],
        "albums_not_found": [],
    }))

    with patch("spotify_client.get_spotify_client"):
        from config import Config
        cfg = Config(
            spotify_client_id="id",
            spotify_client_secret="secret",
            spotify_redirect_uri="http://localhost:8888/callback",
        )
        stats = create_playlists(config=cfg, data_dir=data_dir)
        assert stats["skipped"] >= 1


@patch("spotify_client.get_spotify_client")
@patch("spotify_client.search_album")
@patch("spotify_client.get_album_track_uris")
@patch("spotify_client.add_tracks_batched")
def test_create_playlists_uses_fb_prefix_for_facebook_source(
    mock_batch, mock_uris, mock_search, mock_client, tmp_path
):
    data_dir = str(tmp_path)
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    posts_dir = tmp_path / "posts" / "fb_555"
    posts_dir.mkdir(parents=True)

    (posts_dir / "metadata.json").write_text(json.dumps({
        "shortcode": "fb_555",
        "owner": "facebook",
        "timestamp": "2024-04-25T00:00:00+00:00",
        "url": "https://www.facebook.com/watch/?v=555",
        "source": "facebook",
    }))
    (posts_dir / "caption.txt").write_text("album review video")

    (analysis_dir / "fb_555.json").write_text(json.dumps({
        "transcript": "check out Kid A by Radiohead",
        "albums": [{"artist": "Radiohead", "album": "Kid A"}],
        "has_music": True,
    }))

    mock_sp = MagicMock()
    mock_client.return_value = mock_sp
    mock_sp.current_user.return_value = {"id": "user123"}
    mock_search.return_value = {"id": "album_id_1", "artists": [{"name": "Radiohead"}]}
    mock_uris.return_value = ["spotify:track:1", "spotify:track:2"]
    mock_sp.user_playlist_create.return_value = {
        "id": "pl_123",
        "external_urls": {"spotify": "https://open.spotify.com/playlist/pl_123"},
    }

    from config import Config
    cfg = Config(
        spotify_client_id="id",
        spotify_client_secret="secret",
        spotify_redirect_uri="http://localhost:8888/callback",
    )
    stats = create_playlists(config=cfg, data_dir=data_dir)

    assert stats["processed"] == 1
    call_kwargs = mock_sp.user_playlist_create.call_args
    assert call_kwargs.kwargs.get("name") == "FB: 2024-04-25"
