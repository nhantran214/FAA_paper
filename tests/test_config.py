"""Settings read only the database and SMTP endpoints from the environment."""

from __future__ import annotations

from tonomyx.config import Settings


def test_settings_need_no_canon_pack(monkeypatch) -> None:
    monkeypatch.delenv("TONOMYX_CANON_PACK", raising=False)
    s = Settings.from_env()
    assert not hasattr(s, "canon_pack") and s.database_url


def test_database_url_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("TONOMYX_DATABASE_URL", "postgresql://x:y@example:1/z")
    assert Settings.from_env().database_url == "postgresql://x:y@example:1/z"
