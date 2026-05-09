import os
import pytest


def test_config_loads_defaults(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    for key in ("ADMIN_IDS", "MAX_CONCURRENT_DOWNLOADS", "MAX_FILE_SIZE"):
        monkeypatch.delenv(key, raising=False)

    from bot.config import load_config

    cfg = load_config()
    assert cfg.bot_token == "123:abc"
    assert cfg.max_concurrent_downloads == 2
    assert cfg.max_file_size == 50_000_000
    assert cfg.rate_limit_per_minute == 5
    assert cfg.audio_bitrate == 192
    assert cfg.admin_ids == []


def test_config_loads_admin_ids(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ADMIN_IDS", "111,222,333")

    from bot.config import load_config

    cfg = load_config()
    assert cfg.admin_ids == [111, 222, 333]


def test_config_missing_token_raises(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    from bot.config import load_config

    with pytest.raises(ValueError, match="BOT_TOKEN"):
        load_config()
