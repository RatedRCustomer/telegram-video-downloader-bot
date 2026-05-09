import os
import pytest


@pytest.fixture(autouse=True)
def _env_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test:token")
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path / "downloads"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    os.makedirs(tmp_path / "downloads", exist_ok=True)
