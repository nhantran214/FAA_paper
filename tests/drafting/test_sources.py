import csv
import json
from pathlib import Path

import pytest

from tonomyx.bench.inputs import CaseInputs
from tonomyx.drafting.sources import briefs, case_view

ROLES = "ma_vai,loai,soan_bang,yeu_cau_duyet,duyet_loai\nDP-01,dieu_phoi,,,\n"
CANARY = "ZZ-CANARY"


def make_bench(root: Path, industries: dict[str, str]) -> Path:
    """A tiny bench: ``industries`` maps case id to industry."""
    axes = {
        "industries": [{"id": i, "ten": f"Ngành {i}", "name_en": f"Industry {i}"}
                       for i in sorted(set(industries.values()))],
        "departments": [
            {"id": "mua_hang", "ten": "Mua hàng", "name_en": "Purchasing", "processes": [
                {"id": "procure_to_pay", "ten": "Mua đến trả", "name_en": "Procure to pay"},
                {"id": "refund", "ten": "Hoàn tiền", "name_en": "Refund"}]},
            {"id": "ban", "ten": "Bán hàng", "name_en": "Sales", "processes": [
                {"id": "quote", "ten": "Báo giá", "name_en": "Quote"}]},
        ],
    }
    (root / "axes.json").write_text(json.dumps(axes), encoding="utf-8")
    rows = [
        {"case_id": cid, "industry": ind, "department": "mua_hang",
         "process": "procure_to_pay" if n % 2 == 0 else "refund"}
        for n, (cid, ind) in enumerate(industries.items())
    ]
    (root / "coverage.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    for cid in industries:
        d = root / cid
        (d / "kb").mkdir(parents=True)
        (d / "data").mkdir()
        (d / "roles.csv").write_text(ROLES, encoding="utf-8")
        (d / "policy.json").write_text('{"approval_rules": []}', encoding="utf-8")
        (d / "kb" / "chinh_sach.md").write_text("# Chính sách\nnội dung", encoding="utf-8")
        with (d / "data" / "doi_tac.csv").open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([["ma", "ten"], ["A", "B"]])
        # The answer side and the meta hold a canary that no view may carry.
        (d / "case.meta.json").write_text(
            json.dumps({"industry": "ban_le", "title": CANARY}), encoding="utf-8")
        for name in ("story.md", "process.json", "attacks.json"):
            (d / name).write_text(CANARY, encoding="utf-8")
        (d / "expected").mkdir()
        (d / "expected" / "events.csv").write_text(CANARY, encoding="utf-8")
    return root


def inputs(cid: str) -> CaseInputs:
    return CaseInputs(cid, "Chủ đề", "Yêu cầu trung tính", (), "approved")


def test_briefs_lists_processes_of_the_industries(tmp_path: Path) -> None:
    root = make_bench(tmp_path, {"C1": "san_xuat", "C2": "y_te", "C3": "ban_le"})
    got = briefs(root / "axes.json", ("san_xuat",))
    assert [b.process_id for b in got] == ["procure_to_pay"]
    assert got[0].industry_names == ("Ngành san_xuat (Industry san_xuat)",)
    assert got[0].department_vi == "Mua hàng" and got[0].industries == ("san_xuat",)
    assert [b.process_id for b in briefs(root / "axes.json", ("san_xuat", "y_te"))] == [
        "procure_to_pay", "refund"]


def test_case_view_opens_only_allowed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_bench(tmp_path, {"C1": "san_xuat"})
    opened: list[str] = []
    real_read, real_open = Path.read_text, Path.open

    def read_text(self: Path, *a: object, **k: object) -> str:
        opened.append(str(self))
        return real_read(self, *a, **k)  # type: ignore[arg-type]

    def opener(self: Path, *a: object, **k: object):  # type: ignore[no-untyped-def]
        opened.append(str(self))
        return real_open(self, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(Path, "open", opener)
    view = case_view(root / "C1", inputs("C1"))
    names = {str(Path(p).relative_to(root)) for p in opened}
    assert names == {"C1/roles.csv", "C1/policy.json", "C1/kb/chinh_sach.md",
                     "C1/data/doi_tac.csv"}
    assert view.request == "Yêu cầu trung tính"
    assert CANARY not in json.dumps(view.__dict__, ensure_ascii=False, default=str)


@pytest.mark.parametrize("industry", ["san_xuat", "ban_le"])
def test_case_view_loads_any_industry_and_opens_no_answer_file(
    tmp_path: Path, industry: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_bench(tmp_path, {"C1": industry})
    seen: list[str] = []
    real = Path.read_text
    monkeypatch.setattr(
        Path, "read_text", lambda self, *a, **k: (seen.append(self.name), real(self, *a, **k))[1]
    )
    view = case_view(root / "C1", inputs("C1"))
    assert view.case_id == "C1"
    assert not {"case.meta.json", "story.md", "process.json", "attacks.json"} & set(seen)
    assert CANARY not in json.dumps(view.opening_data) + view.roles_csv
