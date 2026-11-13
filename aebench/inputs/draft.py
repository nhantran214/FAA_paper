"""Drafting case inputs, and the expert sheet that reviews them (spec L8b).

The drafter reads only the title, the story text before its events section, ``roles.csv``,
``data/*.csv`` and the input facts of ``process.json`` (through
``input_fact_candidates``). It never reads ``expected/``, ``attacks.json`` or the rest of
the story, and nothing it reads is printed. Its system prompt names the words a request
must not use (``OUTCOME_WORDS``, final review C1), and the check flags a request that
quotes a candidate fact its allow-list does not hold.

The sheet goes to people outside the project (Task 3 M8): a cell that starts with ``=``,
``+``, ``-`` or ``@`` is written with a leading single quote, so a spreadsheet never reads
it as a formula, and the import takes that quote off again. Sheet rows whose case id the
inputs file does not hold are counted (``unknown``), never applied.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from tonomyx.bench.cases import read_meta
from tonomyx.bench.inputs import (
    OUTCOME_WORDS,
    CaseInputs,
    check_request,
    input_fact_candidates,
    nfc,
)
from tonomyx.models.json_model import JsonModel

STORY_SPLIT = "## Diễn biến"
SHEET_COLUMNS: tuple[str, ...] = (
    "case_id",
    "industry",
    "title",
    "story_opening",
    "subject",
    "request",
    "problems",
    "input_facts",
    "input_fact_values",
    "decision",
    "corrected_subject",
    "corrected_request",
    "corrected_input_facts",
    "override_reason",
    "reviewer",
)
DECISIONS = ("approve", "reject")
MAX_TABLE_ROWS = 5

SYSTEM = (
    "Bạn soạn yêu cầu mở đầu cho một hồ sơ nghiệp vụ. Chỉ viết ai gửi và yêu cầu gì, "
    "tuyệt đối không viết kết quả hay cách hồ sơ kết thúc, không đánh giá đúng sai. "
    "Nếu hồ sơ có thông điệp nhận được, trích nguyên văn nội dung thông điệp đó. "
    "Không chép nguyên văn quá 7 từ liên tiếp từ phần mô tả. "
    'Trả về một đối tượng JSON: {"subject": "dòng tiêu đề trung tính ngắn", '
    '"request": "yêu cầu mở đầu, dưới 400 ký tự", '
    '"input_facts": ["tên các dữ kiện đầu vào được phép tiết lộ"]}. '
    "input_facts chỉ chứa tên trong danh sách ứng viên. "
    "Mọi giá trị của dữ kiện ứng viên mà tiêu đề hoặc yêu cầu nhắc đến phải có tên "
    "trong input_facts. "
    "Tiêu đề và yêu cầu không được dùng các từ sau: " + ", ".join(OUTCOME_WORDS) + "."
)
# A sheet cell a spreadsheet would read as a formula starts with one of these.
FORMULA_STARTS = ("=", "+", "-", "@")


def story_opening(case_dir: Path) -> str:
    """The story text before its events section, without the title line.

    Empty when the case has no story or the story has no events section."""
    path = Path(case_dir) / "story.md"
    if not path.is_file():
        return ""
    text = nfc(path.read_text(encoding="utf-8"))
    if STORY_SPLIT not in text:
        return ""
    head = text.split(STORY_SPLIT, 1)[0]
    lines = head.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _case_id(case_dir: Path) -> str:
    return str(read_meta(case_dir).get("case_id") or Path(case_dir).name)


def _title(case_dir: Path) -> str:
    return nfc(str(read_meta(case_dir).get("title") or ""))


def _csv_text(path: Path, limit: int = MAX_TABLE_ROWS) -> str:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return "\n".join(",".join(r) for r in rows[: limit + 1])


def _prompt(case_dir: Path) -> str:
    case_dir = Path(case_dir)
    parts = [
        f"Tiêu đề: {_title(case_dir)}",
        f"Mô tả mở đầu:\n{story_opening(case_dir)}",
        f"Vai trò:\n{_csv_text(case_dir / 'roles.csv', 50)}",
    ]
    data = case_dir / "data"
    if data.is_dir():
        for table in sorted(data.glob("*.csv")):
            parts.append(f"Bảng {table.stem}:\n{_csv_text(table)}")
    candidates = input_fact_candidates(case_dir)
    parts.append(
        "Dữ kiện ứng viên (tên=giá trị):\n"
        + "\n".join(f"{k}={v}" for k, v in candidates.items())
    )
    return "\n\n".join(parts)


def draft_inputs(
    case_dirs: Iterable[Path],
    model: JsonModel,
    *,
    seed: int,
    on_draft: Callable[[CaseInputs], None] | None = None,
) -> dict[str, CaseInputs]:
    """Draft each case; ``on_draft`` gets every draft as soon as it is made (to save it)."""
    out: dict[str, CaseInputs] = {}
    for case_dir in case_dirs:
        case_dir = Path(case_dir)
        case_id = _case_id(case_dir)
        reply = model.complete_json(SYSTEM, _prompt(case_dir), seed=seed)
        data = reply.data
        allowed = set(input_fact_candidates(case_dir))
        facts = data.get("input_facts") or []
        item = CaseInputs(
            case_id=case_id,
            subject=nfc(str(data.get("subject") or "").strip()),
            request=nfc(str(data.get("request") or "").strip()),
            input_facts=tuple(
                dict.fromkeys(str(n) for n in facts if str(n) in allowed)
            ),
            status="draft",
        )
        out[case_id] = item
        if on_draft is not None:
            on_draft(item)
    return out


def _problems(
    subject: str, request: str, body: str, facts: dict[str, Any], listed: tuple[str, ...]
) -> list[str]:
    found = check_request(request, story_body=body, facts=facts, listed=listed)
    found += [
        f"subject: {p}"
        for p in check_request(subject, story_body=body, what="subject", facts=facts,
                               listed=listed)
    ]
    return found


def problems_of(item: CaseInputs, case_dir: Path) -> list[str]:
    body = f"{_title(case_dir)}\n{story_opening(case_dir)}"
    return _problems(item.subject, item.request, body, input_fact_candidates(case_dir),
                     item.input_facts)


def _safe_cell(value: Any) -> Any:
    """A text cell that a spreadsheet would read as a formula, quoted."""
    if isinstance(value, str) and value.startswith(FORMULA_STARTS):
        return "'" + value
    return value


def _unsafe_cell(value: str | None) -> str | None:
    """The cell as it was before ``_safe_cell`` quoted it."""
    if value and value.startswith("'") and value[1:].startswith(FORMULA_STARTS):
        return value[1:]
    return value


def _sheet_values(cell: str) -> dict[str, Any]:
    """The ``input_fact_values`` column (``name = value`` per line) read back, numbers as
    numbers; used when the case folders are not given."""
    out: dict[str, Any] = {}
    for line in cell.splitlines():
        name, sep, raw = line.partition("=")
        if not sep or not name.strip():
            continue
        text = raw.strip()
        value: Any = text
        for kind in (int, float):
            try:
                value = kind(text)
                break
            except ValueError:
                continue
        out[name.strip()] = value
    return out


def export_sheet(
    inputs: Mapping[str, CaseInputs], case_dirs: Iterable[Path], out_csv: Path
) -> int:
    """Write the expert sheet (UTF-8 with BOM, for Excel); returns the number of rows."""
    count = 0
    with Path(out_csv).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        for case_dir in case_dirs:
            case_dir = Path(case_dir)
            case_id = _case_id(case_dir)
            item = inputs.get(case_id)
            if item is None:
                continue
            row = {
                "case_id": case_id,
                "industry": str(read_meta(case_dir).get("industry") or ""),
                "title": _title(case_dir),
                "story_opening": story_opening(case_dir),
                "subject": item.subject,
                "request": item.request,
                "problems": " | ".join(problems_of(item, case_dir)),
                "input_facts": "; ".join(item.input_facts),
                "input_fact_values": "\n".join(
                    f"{k} = {v}" for k, v in input_fact_candidates(case_dir).items()
                ),
                "reviewer": item.reviewer,
            }
            writer.writerow({k: _safe_cell(v) for k, v in row.items()})
            count += 1
    return count


def _names(cell: str) -> tuple[str, ...]:
    names = (part.split("=", 1)[0].strip() for part in cell.split(";"))
    return tuple(dict.fromkeys(n for n in names if n))


def import_sheet(
    csv_path: Path,
    inputs: Mapping[str, CaseInputs],
    case_dirs: Mapping[str, Path] | None = None,
    report: list[str] | None = None,
    unknown: list[str] | None = None,
) -> dict[str, CaseInputs]:
    """Apply the experts' decisions. A row whose (corrected) request or subject still has
    problems is approved only with an ``override_reason``; otherwise it stays ``draft`` and
    its case id is appended to ``report``. ``case_dirs`` maps case ids to folders (for the
    check); without it the row is checked against its sheet columns. A row whose case id
    the inputs do not hold is skipped and its case id appended to ``unknown``."""
    out = dict(inputs)
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as f:
        rows = [
            {k: _unsafe_cell(v) if isinstance(v, str) else v for k, v in r.items()}
            for r in csv.DictReader(f)
        ]
    for row in rows:
        case_id = (row.get("case_id") or "").strip()
        current = out.get(case_id)
        decision = (row.get("decision") or "").strip().casefold()
        if current is None:
            if (case_id or decision) and unknown is not None:
                unknown.append(case_id)
            continue
        if decision not in DECISIONS:
            continue
        subject = nfc((row.get("corrected_subject") or "").strip()) or current.subject
        request = nfc((row.get("corrected_request") or "").strip()) or current.request
        corrected_facts = (row.get("corrected_input_facts") or "").strip()
        facts = _names(corrected_facts) if corrected_facts else current.input_facts
        reviewer = (row.get("reviewer") or "").strip()
        if case_dirs is not None and case_id in case_dirs:
            allowed = set(input_fact_candidates(case_dirs[case_id]))
        else:
            allowed = set(current.input_facts)
        bad_facts = any(n not in allowed for n in facts)
        override = (row.get("override_reason") or "").strip()
        if decision == "reject":
            out[case_id] = CaseInputs(
                case_id, subject, request, facts, "rejected", reviewer, override
            )
            continue
        if case_dirs is not None and case_id in case_dirs:
            body = f"{_title(case_dirs[case_id])}\n{story_opening(case_dirs[case_id])}"
            values = input_fact_candidates(case_dirs[case_id])
        else:
            body = f"{row.get('title', '')}\n{row.get('story_opening', '')}"
            values = _sheet_values(row.get("input_fact_values") or "")
        candidate = CaseInputs(case_id, subject, request, facts, "draft", reviewer)
        found = _problems(subject, request, body, values, facts)
        blank = not (subject.strip() and request.strip())
        if blank or bad_facts or (found and not override):
            out[case_id] = candidate
            if report is not None:
                report.append(case_id)
            continue
        if not reviewer:
            out[case_id] = candidate
            if report is not None:
                report.append(case_id)
            continue
        out[case_id] = CaseInputs(
            case_id, subject, request, facts, "approved", reviewer, override
        )
    return out

