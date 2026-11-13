"""Comments, docstrings and identifiers are English.

Vietnamese belongs in three places only: canon table and column names, canon status
values, and prompts sent to a language model. Those live inside string literals, so
this check looks at comments, docstrings and identifiers and nothing else.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize

from tonomyx.config import REPO_ROOT

# The platform and the evaluation harness (tests/aebench/test_quality.py was folded in here).
SOURCE_ROOTS = (REPO_ROOT / "tonomyx", REPO_ROOT / "aebench")

# Characters that appear in Vietnamese but not in English.
VIETNAMESE = re.compile(
    "[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợ"
    "ùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)


def _python_files() -> list:
    return sorted(path for root in SOURCE_ROOTS for path in root.rglob("*.py"))


def test_no_comment_is_written_in_vietnamese() -> None:
    offences: list[str] = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT and VIETNAMESE.search(token.string):
                offences.append(
                    f"{path.relative_to(REPO_ROOT)}:{token.start[0]}: {token.string.strip()}"
                )
    assert not offences, "comments must be English:\n" + "\n".join(offences)


def test_no_docstring_is_written_in_vietnamese() -> None:
    offences: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        nodes = [tree, *(n for n in ast.walk(tree) if isinstance(
            n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        ))]
        for node in nodes:
            doc = ast.get_docstring(node)
            if doc and VIETNAMESE.search(doc):
                offences.append(f"{path.relative_to(REPO_ROOT)}: {doc.splitlines()[0]}")
    assert not offences, "docstrings must be English:\n" + "\n".join(offences)


def test_no_identifier_is_written_in_vietnamese() -> None:
    offences: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            name = getattr(node, "name", None) or getattr(node, "id", None)
            if isinstance(name, str) and VIETNAMESE.search(name):
                offences.append(f"{path.relative_to(REPO_ROOT)}: {name}")
    assert not offences, "identifiers must be English:\n" + "\n".join(offences)


def test_the_check_would_catch_a_vietnamese_comment() -> None:
    """Proves the check is real."""
    source = "# đây là chú thích tiếng Việt\nx = 1\n"
    found = [
        t.string
        for t in tokenize.generate_tokens(io.StringIO(source).readline)
        if t.type == tokenize.COMMENT and VIETNAMESE.search(t.string)
    ]
    assert len(found) == 1
