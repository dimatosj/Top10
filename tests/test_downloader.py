import json
import os
import pytest
from unittest.mock import MagicMock, patch


@patch("downloader.instaloader")
def test_download_saved_skips_existing(mock_il, tmp_path):
    from downloader import download_saved

    data_dir = str(tmp_path)
    posts_dir = tmp_path / "posts"
    posts_dir.mkdir()
    (posts_dir / "EXISTING").mkdir()

    mock_loader = MagicMock()
    mock_il.Instaloader.return_value = mock_loader
    mock_profile = MagicMock()
    mock_il.Profile.from_username.return_value = mock_profile

    mock_post = MagicMock()
    mock_post.shortcode = "EXISTING"
    mock_profile.get_saved_posts.return_value = [mock_post]

    download_saved(username="testuser", data_dir=data_dir)
