from bot.downloader.progress import parse_ytdlp_progress, format_progress_bar


class TestParseProgress:
    def test_download_line(self):
        line = "[download]  45.2% of  12.34MiB at  5.67MiB/s ETA 00:01"
        result = parse_ytdlp_progress(line)
        assert result is not None
        assert result["percent"] == 45.2
        assert "5.67" in result["speed"]

    def test_non_download_line(self):
        assert parse_ytdlp_progress("[info] Extracting URL") is None

    def test_hundred_percent(self):
        line = "[download] 100% of  12.34MiB in 00:02"
        result = parse_ytdlp_progress(line)
        assert result is not None
        assert result["percent"] == 100.0

    def test_already_downloaded(self):
        line = "[download]  video.mp4 has already been downloaded"
        assert parse_ytdlp_progress(line) is None


class TestFormatProgressBar:
    def test_zero(self):
        bar = format_progress_bar(0, "0 MB/s")
        assert "0%" in bar

    def test_fifty(self):
        bar = format_progress_bar(50, "5.0 MB/s")
        assert "50%" in bar

    def test_hundred(self):
        bar = format_progress_bar(100, "")
        assert "100%" in bar
