import os
import pytest
from config import load_config


def test_load_config_returns_all_keys(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SPOTIFY_CLIENT_ID=test_id\n"
        "SPOTIFY_CLIENT_SECRET=test_secret\n"
        "SPOTIFY_REDIRECT_URI=http://localhost:8888/callback\n"
    )
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=str(env_file))
    assert cfg.spotify_client_id == "test_id"
    assert cfg.spotify_client_secret == "test_secret"
    assert cfg.spotify_redirect_uri == "http://localhost:8888/callback"


def test_load_config_missing_key_raises(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SPOTIFY_CLIENT_ID=test_id\n")
    monkeypatch.chdir(tmp_path)
    # Clear any previously set environment variables
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    with pytest.raises(SystemExit):
        load_config(env_path=str(env_file))
