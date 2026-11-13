"""Case inputs: the neutral opening request and the input facts a case may release.

What the system sees of a case is a subject line, a neutral request and the input facts
the environment may release (spec L8b), never the case title. They are stored outside the
case folders, in ``data/evaluation/inputs.json``, and a person approves them.

``input_fact_candidates`` reads only ``process.json["facts"]`` of a case, and returns
inputs, never conclusions. ``check_request`` flags a request that gives away how the case
ends, and (given the case's candidate facts) one that quotes the value of a candidate fact
the allow-list does not hold (final review C1): what a request quotes, the reviewer
lists.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast

from tonomyx.bench.environment import is_input
from tonomyx.config import REPO_ROOT

INPUTS_PATH: Path = REPO_ROOT / "data" / "evaluation" / "inputs.json"
INPUTS_VERSION = 1
MAX_REQUEST_CHARS = 400
SHARED_RUN_WORDS = 8
PLACEHOLDER_TEXT = "Hồ sơ mới cần xử lý."

Status = Literal["draft", "approved", "rejected"]
STATUSES: tuple[str, ...] = ("draft", "approved", "rejected")

OUTCOME_WORDS: tuple[str, ...] = (
    "duyệt",
    "phê duyệt",
    "từ chối",
    "chặn",
    "gian lận",
    "giả mạo",
    "lừa đảo",
    "tấn công",
    "sai lệch",
    "vượt",
    "trùng",
    "nghi ngờ",
    "hợp lệ",
    "không hợp lệ",
    "đúng quy định",
    "hoàn tất",
    "thành công",
    "đã thanh toán",
    "đã chi",
    "bị khóa",
    "cảnh báo",
)


@dataclass(frozen=True)
class CaseInputs:
    case_id: str
    subject: str
    request: str
    input_facts: tuple[str, ...]
    status: Status
    reviewer: str = ""
    note: str = ""


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def placeholder_inputs(case_id: str) -> CaseInputs:
    """Inputs for scripted tests only: neutral, no facts, never approved."""
    return CaseInputs(case_id, PLACEHOLDER_TEXT, PLACEHOLDER_TEXT, (), "draft")


def load_inputs(path: Path = INPUTS_PATH) -> dict[str, CaseInputs]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != INPUTS_VERSION:
        raise ValueError(f"{path}: unsupported inputs version {data.get('version')!r}")
    out: dict[str, CaseInputs] = {}
    for case_id, row in data.get("cases", {}).items():
        status = row.get("status", "draft")
        if status not in STATUSES:
            raise ValueError(f"{case_id}: unknown status {status!r}")
        subject = nfc(str(row["subject"]))
        request = nfc(str(row["request"]))
        if status == "approved" and not (subject.strip() and request.strip()):
            raise ValueError(f"{case_id}: an approved row has a blank subject or request")
        out[case_id] = CaseInputs(
            case_id=case_id,
            subject=subject,
            request=request,
            input_facts=tuple(str(n) for n in row.get("input_facts", ())),
            status=cast(Status, status),
            reviewer=str(row.get("reviewer", "")),
            note=str(row.get("note", "")),
        )
    return out


def save_inputs(inputs: dict[str, CaseInputs], path: Path = INPUTS_PATH) -> None:
    cases: dict[str, Any] = {}
    for case_id in sorted(inputs):
        row = asdict(inputs[case_id])
        row.pop("case_id")
        row["input_facts"] = list(row["input_facts"])
        cases[case_id] = row
    text = json.dumps({"version": INPUTS_VERSION, "cases": cases}, ensure_ascii=False, indent=2)
    Path(path).write_text(text + "\n", encoding="utf-8")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", nfc(text).casefold())


def _spaced(text: str) -> str:
    return nfc(text).replace("\u00a0", " ")


# A number as a request writes it: digits, maybe grouped or with a decimal part by "." or
# ",", not inside a code (HH-01, PO_2) or a date (05/03/2026).
_NUMBER = re.compile(r"(?<![\w/\-])\d+(?:[.,]\d+)*(?![\w/\-])")
_GROUPED = re.compile(r"\d{1,3}(?:([.,])\d{3})(?:\1\d{3})*")
MIN_QUOTED_TEXT = 3


def _numbers(text: str) -> set[Decimal]:
    """Every value a number of ``text`` may stand for (``25.000.000`` and ``25,000,000`` are
    25000000; ``0,02`` and ``0.02`` are 0.02; ``1.500`` is 1500 or 1.5)."""
    out: set[Decimal] = set()
    for match in _NUMBER.finditer(text):
        token = match.group()
        seps = re.findall(r"[.,]", token)
        try:
            if not seps or _GROUPED.fullmatch(token):
                out.add(Decimal(re.sub(r"[.,]", "", token)))
            if len(seps) == 1:
                out.add(Decimal(token.replace(",", ".")))
        except InvalidOperation:
            continue
    return out


def quoted_facts(text: str, facts: Mapping[str, Any]) -> list[str]:
    """The names of ``facts`` whose value ``text`` quotes: a number written in any of the
    forms ``_numbers`` reads, or a text of at least ``MIN_QUOTED_TEXT`` characters
    (case-insensitive)."""
    folded = _spaced(text).casefold()
    numbers = _numbers(_spaced(text))
    out: list[str] = []
    for name, value in facts.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            try:
                hit = Decimal(str(value)) in numbers
            except InvalidOperation:
                hit = False
        elif isinstance(value, str):
            needle = _spaced(value).strip().casefold()
            hit = len(needle) >= MIN_QUOTED_TEXT and needle in folded
        else:
            hit = False
        if hit:
            out.append(str(name))
    return out


def check_request(
    request: str,
    *,
    story_body: str,
    what: str = "request",
    facts: Mapping[str, Any] | None = None,
    listed: Iterable[str] = (),
) -> list[str]:
    """Problems of a request: blank, an outcome word (case-insensitive, diacritic-sensitive,
    on word boundaries, phrases across any whitespace), a long copy of the story, length,
    and, given the case's candidate ``facts``, a quoted value of a fact not in ``listed``
    (the allow-list)."""
    text = _spaced(request)
    if not text.strip():
        return [f"empty {what}"]
    problems: list[str] = []
    folded = text.casefold()
    for word in OUTCOME_WORDS:
        pattern = r"\s+".join(re.escape(part) for part in nfc(word).casefold().split())
        if re.search(rf"(?<!\w){pattern}(?!\w)", folded):
            problems.append(f"outcome word: {word}")
    mine = _words(text)
    story = _words(story_body)
    n = SHARED_RUN_WORDS
    runs = {tuple(story[i : i + n]) for i in range(len(story) - n + 1)}
    if any(tuple(mine[i : i + n]) in runs for i in range(len(mine) - n + 1)):
        problems.append(f"shares {SHARED_RUN_WORDS} or more consecutive words with the story")
    if len(text) > MAX_REQUEST_CHARS:
        problems.append(f"longer than {MAX_REQUEST_CHARS} characters")
    allowed = set(listed)
    for name in quoted_facts(text, facts or {}):
        if name not in allowed:
            problems.append(f"quotes un-listed fact {name}")
    return problems


def input_fact_candidates(case_dir: Path) -> dict[str, Any]:
    """The facts of ``process.json`` that are inputs (texts, numbers); nothing else is read."""
    process = json.loads((Path(case_dir) / "process.json").read_text(encoding="utf-8"))
    facts = process.get("facts") or {}
    return {str(k): v for k, v in facts.items() if is_input(v)}
