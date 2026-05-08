import json
import os
import pytest
from unittest.mock import patch, MagicMock
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


def test_check_ytdlp_exits_when_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(SystemExit):
            from fb_downloader import check_ytdlp
            check_ytdlp()


def test_download_video_calls_ytdlp(tmp_path):
    from fb_downloader import download_video
    output_path = str(tmp_path / "video.mp4")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        download_video("https://www.facebook.com/watch/?v=123", output_path, browser="chrome")
        mock_run.assert_called_once_with(
            ["yt-dlp", "--cookies-from-browser", "chrome", "-o", output_path, "https://www.facebook.com/watch/?v=123"],
            capture_output=True,
            check=True,
        )


def test_download_facebook_saved_creates_post_dirs(tmp_path):
    from fb_downloader import download_facebook_saved

    export_dir = tmp_path / "export" / "your_facebook_activity" / "saves_and_collections"
    export_dir.mkdir(parents=True)
    (export_dir / "saves_and_collections_v2.json").write_text(json.dumps({
        "saves_and_collections_v2": [
            {
                "timestamp": 1714000000,
                "title": "Music video",
                "data": [{"text": "Album review"}],
                "attachments": [{"data": [{"external_context": {"url": "https://www.facebook.com/watch/?v=555"}}]}],
            },
        ]
    }))

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    with patch("fb_downloader.check_ytdlp"):
        with patch("fb_downloader.download_video") as mock_dl:
            stats = download_facebook_saved(
                export_path=str(tmp_path / "export"),
                data_dir=str(data_dir),
                browser="chrome",
            )

    assert stats["processed"] == 1
    assert stats["skipped"] == 0
    assert stats["failed"] == 0

    post_dir = data_dir / "posts" / "fb_555"
    assert post_dir.exists()
    assert (post_dir / "caption.txt").read_text() == "Album review"

    meta = json.loads((post_dir / "metadata.json").read_text())
    assert meta["shortcode"] == "fb_555"
    assert meta["source"] == "facebook"
    assert meta["url"] == "https://www.facebook.com/watch/?v=555"
    assert meta["owner"] == "facebook"

    mock_dl.assert_called_once_with(
        "https://www.facebook.com/watch/?v=555",
        str(post_dir / "video.mp4"),
        browser="chrome",
    )


def test_download_facebook_saved_skips_existing(tmp_path):
    from fb_downloader import download_facebook_saved

    export_dir = tmp_path / "export" / "your_facebook_activity" / "saves_and_collections"
    export_dir.mkdir(parents=True)
    (export_dir / "saves_and_collections_v2.json").write_text(json.dumps({
        "saves_and_collections_v2": [
            {
                "timestamp": 1714000000,
                "title": "Already downloaded",
                "data": [{"text": "Old"}],
                "attachments": [{"data": [{"external_context": {"url": "https://www.facebook.com/watch/?v=555"}}]}],
            },
        ]
    }))

    data_dir = tmp_path / "data"
    post_dir = data_dir / "posts" / "fb_555"
    post_dir.mkdir(parents=True)

    with patch("fb_downloader.check_ytdlp"):
        with patch("fb_downloader.download_video") as mock_dl:
            stats = download_facebook_saved(
                export_path=str(tmp_path / "export"),
                data_dir=str(data_dir),
                browser="chrome",
            )

    assert stats["skipped"] == 1
    assert stats["processed"] == 0
    mock_dl.assert_not_called()


def test_fb_download_cli_invokes_downloader(tmp_path):
    from click.testing import CliRunner
    from ig2spotify import cli

    runner = CliRunner()
    with patch("fb_downloader.download_facebook_saved") as mock_dl:
        mock_dl.return_value = {"processed": 1, "skipped": 0, "failed": 0}
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "fb-download",
            "--export-path", "/some/export",
            "--browser", "firefox",
        ])
    assert result.exit_code == 0
    mock_dl.assert_called_once_with(
        export_path="/some/export",
        data_dir=str(tmp_path),
        browser="firefox",
    )


def test_fb_run_cli_invokes_download_then_extract(tmp_path):
    from click.testing import CliRunner
    from ig2spotify import cli

    runner = CliRunner()
    with patch("fb_downloader.download_facebook_saved") as mock_dl:
        with patch("extractor.extract_all_audio") as mock_extract:
            mock_dl.return_value = {"processed": 1, "skipped": 0, "failed": 0}
            mock_extract.return_value = {"processed": 1, "skipped": 0, "failed": 0}
            result = runner.invoke(cli, [
                "--data-dir", str(tmp_path),
                "fb-run",
                "--export-path", "/some/export",
            ])
    assert result.exit_code == 0
    mock_dl.assert_called_once()
    mock_extract.assert_called_once()
    assert "Audio extracted" in result.output
