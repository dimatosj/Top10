import json
import os
import pytest
from unittest.mock import MagicMock, patch, call
from spotify_client import (
    build_search_query, add_tracks_batched, create_playlists,
    _names_close, _levenshtein,
)


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


class TestNamesClose:
    def test_exact_match(self):
        assert _names_close("Radiohead", "Radiohead")

    def test_case_insensitive(self):
        assert _names_close("radiohead", "RADIOHEAD")

    def test_punctuation_stripped(self):
        assert _names_close("Guns N' Roses", "Guns N Roses")
        assert _names_close("OK Computer", "OK, Computer")

    def test_semicolon_stripped(self):
        assert _names_close(
            "Lucro Sucio y Los Ojos del Vacio",
            "Lucro sucio; Los ojos del vacio",
        )

    def test_ampersand_and(self):
        assert _names_close("Simon & Garfunkel", "Simon and Garfunkel")

    def test_substring_similar_length(self):
        assert _names_close("caroline", "caroline 2")

    def test_substring_too_short(self):
        assert not _names_close("Sucio", "Lucro Sucio y Los Ojos del Vacio")

    def test_small_edit_distance(self):
        assert _names_close("Deafheaven", "Deafhaven")

    def test_completely_different(self):
        assert not _names_close("Radiohead", "Taylor Swift")

    def test_short_strings_no_false_match(self):
        assert not _names_close("1234", "Fake Album Title 12345")

    def test_empty_strings(self):
        assert _names_close("", "")
        assert not _names_close("", "something")


class TestLevenshtein:
    def test_identical(self):
        assert _levenshtein("abc", "abc") == 0

    def test_empty(self):
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3

    def test_single_insertion(self):
        assert _levenshtein("abc", "abcd") == 1

    def test_single_deletion(self):
        assert _levenshtein("abcd", "abc") == 1

    def test_substitution(self):
        assert _levenshtein("abc", "axc") == 1

    def test_completely_different(self):
        assert _levenshtein("abc", "xyz") == 3


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
    }))
    (posts_dir / "caption.txt").write_text("no music here")

    (analysis_dir / "ABC123.json").write_text(json.dumps({
        "transcript": "just a random video",
        "albums": [],
        "has_music": False,
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
        assert not (tmp_path / "playlists" / "ABC123.json").exists()


def test_create_playlists_skips_existing_playlist(tmp_path):
    data_dir = str(tmp_path)
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    playlists_dir = tmp_path / "playlists"
    playlists_dir.mkdir()

    (analysis_dir / "XYZ789.json").write_text(json.dumps({
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
def test_create_playlists_names_with_owner_and_genre(
    mock_batch, mock_uris, mock_search, mock_client, tmp_path
):
    data_dir = str(tmp_path)
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    posts_dir = tmp_path / "posts" / "fb_555"
    posts_dir.mkdir(parents=True)

    (posts_dir / "metadata.json").write_text(json.dumps({
        "shortcode": "fb_555",
        "owner": "Josey Records",
        "timestamp": "2024-04-25T00:00:00+00:00",
    }))
    (posts_dir / "caption.txt").write_text("album review video")

    (analysis_dir / "fb_555.json").write_text(json.dumps({
        "albums": [{"artist": "Radiohead", "album": "Kid A"}],
        "has_music": True,
        "genre": "Alternative & Indie",
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
    assert call_kwargs.kwargs.get("name") == "@Josey Records [Alternative & Indie]"
