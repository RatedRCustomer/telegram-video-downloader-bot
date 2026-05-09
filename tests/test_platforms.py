import pytest
from bot.downloader.platforms import (
    Platform,
    MediaType,
    DownloadTool,
    extract_urls,
    identify_platform,
    is_short_url,
)


class TestExtractUrls:
    def test_single_url(self):
        urls = extract_urls("check this https://youtube.com/watch?v=abc123")
        assert urls == ["https://youtube.com/watch?v=abc123"]

    def test_multiple_urls(self):
        text = "vid1 https://youtube.com/watch?v=a vid2 https://tiktok.com/@user/video/123"
        urls = extract_urls(text)
        assert len(urls) == 2

    def test_no_urls(self):
        assert extract_urls("just regular text") == []

    def test_url_with_surrounding_text(self):
        urls = extract_urls("hey look https://youtu.be/abc123 nice video")
        assert urls == ["https://youtu.be/abc123"]


class TestIdentifyPlatform:
    @pytest.mark.parametrize(
        "url, expected_platform",
        [
            ("https://youtube.com/watch?v=abc", Platform.YOUTUBE),
            ("https://www.youtube.com/watch?v=abc", Platform.YOUTUBE),
            ("https://youtu.be/abc123", Platform.YOUTUBE),
            ("https://m.youtube.com/watch?v=abc", Platform.YOUTUBE),
            ("https://youtube.com/shorts/abc123", Platform.YOUTUBE),
            ("https://music.youtube.com/watch?v=abc", Platform.YOUTUBE_MUSIC),
            ("https://instagram.com/reel/abc123/", Platform.INSTAGRAM),
            ("https://www.instagram.com/p/abc123/", Platform.INSTAGRAM),
            ("https://tiktok.com/@user/video/123", Platform.TIKTOK),
            ("https://www.tiktok.com/@user/video/123", Platform.TIKTOK),
            ("https://twitter.com/user/status/123", Platform.TWITTER),
            ("https://x.com/user/status/123", Platform.TWITTER),
            ("https://pinterest.com/pin/123/", Platform.PINTEREST),
            ("https://www.pinterest.com/pin/123/", Platform.PINTEREST),
            ("https://www.threads.net/@user/post/abc", Platform.THREADS),
            ("https://soundcloud.com/artist/track", Platform.SOUNDCLOUD),
            ("https://open.spotify.com/track/abc123", Platform.SPOTIFY),
            ("https://deezer.com/track/123", Platform.DEEZER),
            ("https://www.deezer.com/en/track/123", Platform.DEEZER),
            ("https://vk.com/video-123_456", Platform.VK),
            ("https://www.vk.com/video123_456", Platform.VK),
            ("https://m.vk.com/video-123_456", Platform.VK),
            ("https://vk.ru/video-123_456", Platform.VK),
            ("https://vkvideo.ru/video-123_456", Platform.VK),
            ("https://vk.com/clip-123_456", Platform.VK),
        ],
    )
    def test_known_platforms(self, url, expected_platform):
        match = identify_platform(url)
        assert match is not None
        assert match.platform == expected_platform

    def test_unknown_url_returns_none(self):
        assert identify_platform("https://example.com/article") is None
        assert identify_platform("https://bbc.com/news/123") is None

    def test_audio_platforms_return_audio_type(self):
        for url in [
            "https://music.youtube.com/watch?v=abc",
            "https://open.spotify.com/track/abc",
            "https://deezer.com/track/123",
            "https://soundcloud.com/artist/track",
        ]:
            match = identify_platform(url)
            assert match is not None
            assert match.media_type == MediaType.AUDIO, f"Expected AUDIO for {url}"

    def test_video_platforms_return_video_type(self):
        for url in [
            "https://youtube.com/watch?v=abc",
            "https://instagram.com/reel/abc/",
            "https://tiktok.com/@user/video/123",
            "https://x.com/user/status/123",
        ]:
            match = identify_platform(url)
            assert match is not None
            assert match.media_type == MediaType.VIDEO, f"Expected VIDEO for {url}"

    def test_pinterest_uses_gallery_dl(self):
        match = identify_platform("https://pinterest.com/pin/123/")
        assert match is not None
        assert match.tool == DownloadTool.GALLERY_DL

    def test_spotify_uses_spotdl(self):
        match = identify_platform("https://open.spotify.com/track/abc")
        assert match is not None
        assert match.tool == DownloadTool.SPOTDL


class TestShortUrls:
    @pytest.mark.parametrize(
        "url",
        [
            "https://vm.tiktok.com/abc123/",
            "https://vt.tiktok.com/abc123/",
            "https://t.co/abc123",
            "https://pin.it/abc123",
            "https://spotify.link/abc123",
            "https://deezer.page.link/abc123",
            "https://on.soundcloud.com/abc123",
            "https://vk.cc/abc123",
        ],
    )
    def test_short_urls_detected(self, url):
        assert is_short_url(url) is True

    def test_regular_urls_not_short(self):
        assert is_short_url("https://youtube.com/watch?v=abc") is False
        assert is_short_url("https://tiktok.com/@user/video/123") is False
