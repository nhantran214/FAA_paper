"""Point every test at this project's own database before anything imports settings.

The vendored tonomyx package defaults to the TonomyX checkout's database on port
55432. Benchmark tests reset and rebuild the schema, so they must never land there.
An explicit TONOMYX_DATABASE_URL in the environment still wins.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "TONOMYX_DATABASE_URL", "postgresql://tonomyx:tonomyx@localhost:55433/tonomyx"
)
