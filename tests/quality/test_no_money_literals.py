"""No amount of money may be written into the source.

The canon leaves every amount blank on purpose: the source books establish none.
An amount in the code would be an invented business fact. Money comes from
data/illustrative/prices.csv, which is labelled non-canon, or from the database.
"""

from __future__ import annotations

import ast

from tonomyx.config import REPO_ROOT

# The platform and the evaluation harness (tests/aebench/test_quality.py was folded in here).
SOURCE_ROOTS = (REPO_ROOT / "tonomyx", REPO_ROOT / "aebench")

# Large integers that are plainly not money.
ALLOWED = frozenset(
    {
        32768,  # models.chat: Ollama context window asked for, in tokens
        4096,  # models.chat: longest reply Ollama may generate, in tokens
        4000,  # executors.model: longest tool reply handed back to a model, in characters
    }
)

THRESHOLD = 1000


def test_no_large_integer_literals_outside_the_allowlist() -> None:
    offences: list[str] = []
    for path in sorted(path for root in SOURCE_ROOTS for path in root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int)
                and not isinstance(node.value, bool)
                and node.value >= THRESHOLD
                and node.value not in ALLOWED
            ):
                offences.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {node.value}")
    assert not offences, "possible hard-coded money:\n" + "\n".join(offences)


def test_the_scan_would_catch_a_planted_amount(tmp_path) -> None:
    """Proves the scan is real."""
    planted = tmp_path / "planted.py"
    planted.write_text("TOTAL = 288000000\n", encoding="utf-8")
    tree = ast.parse(planted.read_text(encoding="utf-8"))
    found = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, int) and n.value >= THRESHOLD
    ]
    assert found == [288000000]
