import pytest
from bot.downloader.engine import DownloadEngine
from bot.downloader.platforms import MediaType
from bot.config import Config


@pytest.fixture
def config(tmp_path):
    return Config(
        bot_token="test:token",
        download_dir=str(tmp_path / "downloads"),
        db_path=str(tmp_path / "test.db"),
        max_file_size=50_000_000,
        audio_bitrate=192,
    )


@pytest.fixture
def engine(config, tmp_path):
    import os
    os.makedirs(config.download_dir, exist_ok=True)
    return DownloadEngine(config)


class TestBuildYtdlpArgs:
    def test_video_auto_quality(self, engine):
        args = engine._build_ytdlp_args(
            "https://youtube.com/watch?v=abc", MediaType.VIDEO, "auto",
        )
        assert "yt-dlp" in args[0]
        assert any("bestvideo" in a for a in args)
        assert "--merge-output-format" in args

    def test_video_specific_quality(self, engine):
        args = engine._build_ytdlp_args(
            "https://youtube.com/watch?v=abc", MediaType.VIDEO, "720",
        )
        assert any("720" in a for a in args)

    def test_audio_format(self, engine):
        args = engine._build_ytdlp_args(
            "https://youtube.com/watch?v=abc", MediaType.AUDIO, "auto",
        )
        assert "--extract-audio" in args
        assert "--audio-format" in args


class TestBuildSpotdlArgs:
    def test_spotify_url(self, engine):
        args = engine._build_spotdl_args("https://open.spotify.com/track/abc")
        assert "spotdl" in args[0]
        assert "https://open.spotify.com/track/abc" in args


class TestBuildGalleryDlArgs:
    def test_pinterest_url(self, engine):
        args = engine._build_gallery_dl_args("https://pinterest.com/pin/123/")
        assert "gallery-dl" in args[0]
        assert "https://pinterest.com/pin/123/" in args


class TestUrlHash:
    def test_same_url_same_hash(self, engine):
        h1 = engine.url_hash("https://youtube.com/watch?v=abc", "auto")
        h2 = engine.url_hash("https://youtube.com/watch?v=abc", "auto")
        assert h1 == h2

    def test_different_quality_different_hash(self, engine):
        h1 = engine.url_hash("https://youtube.com/watch?v=abc", "auto")
        h2 = engine.url_hash("https://youtube.com/watch?v=abc", "720")
        assert h1 != h2
