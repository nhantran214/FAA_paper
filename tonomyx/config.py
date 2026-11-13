"""Runtime configuration, read once from the environment.

Only the database and SMTP endpoints come from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DATABASE_URL = "postgresql://tonomyx:tonomyx@localhost:55432/tonomyx"


@dataclass(frozen=True)
class Settings:
    """Everything the process needs from its environment."""

    database_url: str
    smtp_host: str
    smtp_port: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get("TONOMYX_DATABASE_URL", DEFAULT_DATABASE_URL),
            smtp_host=os.environ.get("TONOMYX_SMTP_HOST", "localhost"),
            smtp_port=int(os.environ.get("TONOMYX_SMTP_PORT", "1025")),
        )
