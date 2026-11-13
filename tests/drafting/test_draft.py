import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from tests.drafting.test_sources import CANARY, inputs, make_bench
from tonomyx.bench.inputs import placeholder_inputs
from tonomyx.drafting.draft import MAX_ROUNDS, draft_set
from tonomyx.drafting.prompts import TOY_TEMPLATE, system_prompt, user_prompt
from tonomyx.drafting.sources import ProcessBrief, case_view
from tonomyx.governance.template import load_template
from tonomyx.governance.validate import validate
from tonomyx.models.identity import ModelIdentity
from tonomyx.models.json_model import JsonReply, ModelError

REPO = Path(__file__).resolve().parents[2]
BRIEF = ProcessBrief("procure_to_pay", "Mua đến trả", "Procure to pay", "mua_hang", "Mua hàng",
                     ("san_xuat",), ("Sản xuất (Manufacturing)",))
IDENT = ModelIdentity("fake", "hosted:fake")

ROLES = (
    "ma_vai,loai,soan_bang,yeu_cau_duyet,duyet_loai\nDP-01,dieu_phoi,,,\n"
    "DE-01,so,chung_tu,t,\nKTT-01,nguoi,,,de_nghi_chi\n"
)


def good_template(process_id: str = "procure_to_pay") -> dict[str, Any]:
    t = deepcopy(TOY_TEMPLATE)
    t["id"] = process_id
    t["roles"][2]["duties"]["decides"] = ["de_nghi_chi"]
    return t


class Fake:
    name = "fake"

    def __init__(self, replies: list[Any]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str, *, seed: int) -> JsonReply:
        self.calls.append((system, user))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return JsonReply(reply)


class _Hosted(Fake):
    name = "gemini-fake"


def run(model: Fake, tmp_path: Path, mode: str = "blind", views: Any = None,
        briefs: Any = None) -> Any:
    return draft_set("set1", mode, briefs or [BRIEF], views or {}, model, tmp_path,  # type: ignore[arg-type]
                     seed=3, engine_fingerprint="unfrozen", identity=IDENT)


def bench_templates() -> list[dict[str, Any]]:
    paths = list((REPO / "tests" / "fixtures" / "governance").rglob("templates/**/*.json"))
    paths += list((REPO / "tests" / "fixtures").glob("canon_pack_*/**/*template*.json"))
    return [json.loads(p.read_text(encoding="utf-8")) for p in paths]


def test_toy_example_is_valid_and_outside_bench(tmp_path: Path) -> None:
    p = tmp_path / "toy.json"
    p.write_text(json.dumps(TOY_TEMPLATE), encoding="utf-8")
    assert [f for f in validate(load_template(p)) if f.level == "error"] == []
    axes = json.loads((REPO / "data" / "bench_v1" / "axes.json").read_text(encoding="utf-8"))
    ids = {p["id"] for d in axes["departments"] for p in d["processes"]}
    assert TOY_TEMPLATE["id"] not in ids


def test_blind_prompt_contains_no_case_text(tmp_path: Path) -> None:
    root = make_bench(tmp_path, {"C1": "san_xuat"})
    view = case_view(root / "C1", inputs("C1"))
    prompts = system_prompt() + user_prompt(BRIEF, "blind", [view])
    for text in (view.request, view.roles_csv, view.policy_json, *view.kb.values(),
                 *view.opening_data.values(), CANARY):
        assert text not in prompts
    templates = bench_templates()
    assert templates
    for t in templates:
        texts = [t["name"]] + [s["guidance"] for s in t["steps"] if s.get("guidance")]
        texts += [s["params"].get("reason", "") for s in t["steps"]]
        for text in texts:
            if text and text != "Hoàn tất":
                assert text not in prompts, text
    for industry in BRIEF.industry_names:
        assert industry in prompts
    # The toy is the only template in the prompt.
    assert TOY_TEMPLATE["name"] in prompts


def test_informed_prompt_contains_views(tmp_path: Path) -> None:
    root = make_bench(tmp_path, {"C1": "san_xuat"})
    view = case_view(root / "C1", inputs("C1"))
    model = Fake([good_template()])
    run(model, tmp_path / "out", "informed", {"procure_to_pay": [view]})
    user = model.calls[0][1]
    assert view.request in user and view.roles_csv in user and view.policy_json in user
    assert "Chính sách" in user and "C1" not in user
    assert CANARY not in user


def test_blind_mode_sends_no_views_even_if_given(tmp_path: Path) -> None:
    root = make_bench(tmp_path, {"C1": "san_xuat"})
    view = case_view(root / "C1", inputs("C1"))
    model = Fake([good_template()])
    run(model, tmp_path / "out", "blind", {"procure_to_pay": [view]})
    assert view.request not in model.calls[0][1]


def test_invalid_reply_repaired_with_findings(tmp_path: Path) -> None:
    model = Fake([ModelError("not json"), good_template()])
    [r] = run(model, tmp_path)
    assert r.status == "valid" and r.rounds == 2
    assert "not json" in model.calls[1][1]
    bad = good_template()
    bad["steps"][0]["type"] = "no_such_step"
    model = Fake([bad, good_template()])
    [r] = run(model, tmp_path / "b")
    assert r.status == "valid" and r.rounds == 2
    assert "no_such_step" in model.calls[1][1]


def test_wrong_id_is_a_finding(tmp_path: Path) -> None:
    model = Fake([good_template("other"), good_template()])
    [r] = run(model, tmp_path)
    assert r.rounds == 2 and "must be 'procure_to_pay'" in model.calls[1][1]


def test_gives_up_after_one_draft_and_three_repairs_marks_invalid(tmp_path: Path) -> None:
    bad = good_template()
    del bad["start"]
    model = Fake([bad])
    [r] = run(model, tmp_path)
    assert MAX_ROUNDS == 4 and r.status == "invalid" and r.rounds == 4
    assert len(model.calls) == 4 and r.findings
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["processes"]["procure_to_pay"]["status"] == "invalid"


def test_manifest_hashes_match_files(tmp_path: Path) -> None:
    second = ProcessBrief("refund", "Hoàn tiền", "Refund", "mua_hang", "Mua hàng", ("san_xuat",))
    model = Fake([good_template("procure_to_pay"), good_template("refund")])
    results = run(model, tmp_path, briefs=[BRIEF, second])
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert {"name", "mode", "model", "model_digest", "prompt_hash", "seed",
            "engine_fingerprint", "drafted_at", "processes"} <= set(manifest)
    assert manifest["engine_fingerprint"] == "unfrozen" and manifest["seed"] == 3
    assert manifest["model_digest"] == "hosted:fake"
    for r in results:
        file = tmp_path / "templates" / f"{r.process_id}.json"
        entry = manifest["processes"][r.process_id]
        assert entry["sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()
        assert entry["rounds"] == 1 and entry["status"] == "valid"


def test_informed_requires_binding_to_every_source_case(tmp_path: Path) -> None:
    root = make_bench(tmp_path, {"C1": "san_xuat", "C2": "y_te"})
    # Task 14: C2's company has no digital employee (no role of kind so): the template
    # cannot be mapped there.
    (root / "C2" / "roles.csv").write_text(
        ROLES.replace("DE-01,so,chung_tu,t,\n", ""), encoding="utf-8")
    (root / "C1" / "roles.csv").write_text(ROLES, encoding="utf-8")
    views = {"procure_to_pay": [case_view(root / c, placeholder_inputs(c)) for c in ("C1", "C2")]}
    model = Fake([good_template()])
    [r] = run(model, tmp_path / "out", "informed", views)
    assert r.status == "invalid"
    assert any("company 2" in f and "BINDING" in f for f in r.findings)
    assert not any("company 1" in f and "BINDING" in f for f in r.findings)
    # A company whose person decides another approval type: mapped by the best overlap, a
    # warning (INEXACT_BINDING), not an error.
    (root / "C2" / "roles.csv").write_text(
        ROLES.replace("de_nghi_chi", "khac"), encoding="utf-8")
    views = {"procure_to_pay": [case_view(root / c, placeholder_inputs(c)) for c in ("C1", "C2")]}
    [r] = run(Fake([good_template()]), tmp_path / "inexact", "informed", views)
    assert r.status == "valid"
    assert any("company 2" in f and "INEXACT_BINDING" in f for f in r.findings)
    assert not any("company 1" in f and "INEXACT_BINDING" in f for f in r.findings)
    # Bound to the one company it fits: valid.
    ok = {"procure_to_pay": views["procure_to_pay"][:1]}
    [r] = run(Fake([good_template()]), tmp_path / "ok", "informed", ok)
    assert r.status == "valid"


def test_informed_with_no_views_is_invalid_without_calling_the_model(tmp_path: Path) -> None:
    model = Fake([good_template()])
    [r] = run(model, tmp_path, "informed", {})
    assert r.status == "invalid" and r.rounds == 0 and r.template_path is None
    assert r.findings == ["no source cases"] and model.calls == []


def test_stale_template_is_deleted_and_manifest_survives_abort(tmp_path: Path) -> None:
    from tonomyx.models.json_model import ModelUnavailable

    second = ProcessBrief("refund", "Hoàn tiền", "Refund", "mua_hang", "Mua hàng", ("san_xuat",))
    stale = tmp_path / "templates" / "refund.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    model = Fake([good_template(), ModelUnavailable("down")])
    with pytest.raises(ModelUnavailable):
        run(model, tmp_path, briefs=[BRIEF, second])
    assert not stale.exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert list(manifest["processes"]) == ["procure_to_pay"]
    assert manifest["processes"]["procure_to_pay"]["sha256"]


def test_informed_pack_is_the_case_pack(tmp_path: Path) -> None:
    from tonomyx.drafting.draft import pack_of_view

    root = make_bench(tmp_path, {"C1": "san_xuat"})
    pack = pack_of_view(case_view(root / "C1", inputs("C1")))
    assert pack.name == "C1" and pack.version == "bench"


def _cli_bench(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str) -> list[str]:
    import aebench.cli as cli
    from tonomyx.bench.inputs import CaseInputs, save_inputs

    (tmp_path / "bench").mkdir()
    root = make_bench(tmp_path / "bench", {"C1": "ban_le", "C2": "ban_le"})
    monkeypatch.setattr(cli, "BENCH_ROOT", root)
    # This repo's own tonomyx/ may be unclean while it is developed; a paper industry
    # needs a fingerprint (tests/bench/test_freeze.py covers the refusal).
    monkeypatch.setattr(cli, "engine_fingerprint", lambda: "f" * 64)
    monkeypatch.setattr(cli, "create_json_model", lambda name, **k: _Hosted([good_template()]))
    items = {
        c: CaseInputs(c, "s", "r", (), status if c == "C2" else "approved")  # type: ignore[arg-type]
        for c in ("C1", "C2")
    }
    save_inputs(items, tmp_path / "inputs.json")
    return ["draft", "--mode", "informed", "--industries", "ban_le", "--name", "x",
            "--out", str(tmp_path / "out"), "--inputs", str(tmp_path / "inputs.json")]


def test_informed_paper_cli_refuses_unapproved_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from aebench.cli import main

    argv = _cli_bench(tmp_path, monkeypatch, "draft")
    assert main(argv) == 2
    out = capsys.readouterr().out
    assert out.strip() == "refused: cases=2 without_approved_input=1"
    assert not (tmp_path / "out").exists()


def test_informed_paper_cli_runs_when_all_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from aebench.cli import main

    argv = _cli_bench(tmp_path, monkeypatch, "approved")
    main(argv)
    out = capsys.readouterr().out
    assert "placeholder_inputs=0" in out and "refused" not in out
    assert (tmp_path / "out" / "manifest.json").exists()
