import os
import subprocess
import pytest
from extractor import check_ffmpeg, extract_audio, extract_all_audio


def test_check_ffmpeg_raises_when_missing(monkeypatch):
    def mock_run(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(SystemExit):
        check_ffmpeg()


def test_extract_audio_creates_mp3(tmp_path):
    # Create a minimal valid video file using ffmpeg
    video_path = str(tmp_path / "video.mp4")
    audio_path = str(tmp_path / "audio.mp3")
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
    extract_audio(video_path, audio_path)
    assert os.path.exists(audio_path)
    assert os.path.getsize(audio_path) > 0


def test_extract_all_audio_skips_existing(tmp_path):
    posts_dir = tmp_path / "posts"
    post_dir = posts_dir / "ABC123"
    post_dir.mkdir(parents=True)

    # Create a minimal video
    video_path = str(post_dir / "video.mp4")
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

    # Pre-create audio file to test skip logic
    audio_path = post_dir / "audio.mp3"
    audio_path.write_bytes(b"existing audio")

    stats = extract_all_audio(data_dir=str(tmp_path))
    assert stats["skipped"] == 1
    assert stats["processed"] == 0
    # Existing file should be untouched
    assert audio_path.read_bytes() == b"existing audio"
