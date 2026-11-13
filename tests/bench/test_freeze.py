"""The freeze and the paper unlock (spec C10, L8).

Every engine check runs on a temporary git repository with its own ``tonomyx/`` file,
every set check on a temporary set folder, and the unlock-allowed path on a temporary
case folder of a paper industry with synthetic content. No real paper case is opened,
and no git command touches this repository.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tonomyx.bench import freeze
from tonomyx.bench.cases import PAPER_INDUSTRIES, PaperCaseRefused, answer_side
from tonomyx.bench.freeze import (
    EngineDirty,
    EvaluationUnlock,
    FreezeError,
    SetChanged,
    UnlockRefused,
    engine_fingerprint,
    freeze_engine,
    freeze_set,
    is_issued,
    set_hash,
    unlock_paper,
    verify_set,
)

# Inside each temporary repository: the freeze records, the sets and the inputs file, all
# committed before an unlock (final review I7).
FREEZE_REL = "data/evaluation/freeze"
GOV_REL = "data/evaluation/governance"
INPUTS_TEXT = '{"version": 1, "cases": {}}\n'
INPUTS_SHA = hashlib.sha256(INPUTS_TEXT.encode("utf-8")).hexdigest()
ENGINE_AT = "2026-11-10T09:00:00+00:00"
BEFORE = "2026-11-10T08:59:59+00:00"
STARTED = "2026-11-10T09:30:00+00:00"
AFTER = "2026-11-10T10:00:00+00:00"
UNSET = object()


@pytest.fixture(autouse=True)
def _freeze_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set records go to the temporary repository's freeze folder, never this repo's
    data/evaluation/."""
    import aebench.cli as cli

    folder = tmp_path / "repo" / FREEZE_REL
    monkeypatch.setattr(freeze, "FREEZE_DIR", folder)
    monkeypatch.setattr(cli, "FREEZE_DIR", folder)
    return folder


HEADS = {name: {"head": "a" * 40, "clean": True} for name in freeze.BASELINE_CLONES}
PACKAGES = "b" * 64


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The vendored clones' heads and the installed packages' hash, as the freeze reads them
    (final ruling I3): fixed values a test may change, so no test reads this machine's clones
    or venv."""
    state: dict[str, Any] = {"heads": copy.deepcopy(HEADS), "packages": PACKAGES}
    monkeypatch.setattr(freeze, "baseline_heads",
                        lambda root=None: copy.deepcopy(state["heads"]))
    monkeypatch.setattr(freeze, "packages_sha256", lambda: state["packages"])
    return state


# --- temporary git repositories ----------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    done = subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        check=True, capture_output=True, text=True, env=env,
    )
    return done.stdout


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "tonomyx" / "core").mkdir(parents=True)
    (root / "tonomyx" / "engine.py").write_text("X = 1\n", encoding="utf-8")
    (root / "tonomyx" / "core" / "rules.py").write_text("Y = 2\n", encoding="utf-8")
    (root / "README.md").write_text("not the engine\n", encoding="utf-8")
    for rel in ("aebench/arms/guards.py", "aebench/analysis/stats.py", "aebench/report/r.py"):
        (root / rel).parent.mkdir(parents=True)
        (root / rel).write_text("Z = 1\n", encoding="utf-8")
    (root / freeze.INPUTS_REL).parent.mkdir(parents=True)
    (root / freeze.INPUTS_REL).write_text(INPUTS_TEXT, encoding="utf-8")
    _git(root, "init", "-q")
    _commit(root, "init")
    return root


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _freeze_at(monkeypatch: pytest.MonkeyPatch, when: str) -> None:
    monkeypatch.setattr(freeze, "_now", lambda: when)


def _engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, commit: bool = True
) -> tuple[Path, Path, str]:
    """A temporary repo frozen at ENGINE_AT, its engine record committed: (root, freeze
    file, fingerprint)."""
    root = _repo(tmp_path)
    _freeze_at(monkeypatch, ENGINE_AT)
    path = root / FREEZE_REL / "engine.json"
    frozen = freeze_engine(path, root=root)
    if commit:
        _commit(root, "freeze the engine")
    return root, path, frozen.fingerprint


# --- temporary set folders ---------------------------------------------------------------


def _set(
    parent: Path, name: str, mode: str, fingerprint: str, drafted_at: str = AFTER,
    processes: tuple[str, ...] = ("procure_to_pay", "order_to_cash"),
    started_at: object = UNSET, inputs_sha256: str | None = INPUTS_SHA,
) -> Path:
    """A set folder in the shape ``draft_set`` writes."""
    set_dir = parent / name
    (set_dir / "templates").mkdir(parents=True)
    entries: dict[str, Any] = {}
    for pid in processes:
        path = set_dir / "templates" / f"{pid}.json"
        path.write_text(json.dumps({"id": pid, "steps": []}) + "\n", encoding="utf-8")
        entries[pid] = {"status": "valid", "sha256": freeze._sha(path), "rounds": 1}
    manifest = {
        "name": name, "mode": mode, "model": "fake", "model_digest": "hosted:fake",
        "prompt_hash": "0" * 64, "seed": 0, "engine_fingerprint": fingerprint,
        "started_at": STARTED if started_at is UNSET else started_at,
        "drafted_at": drafted_at, "processes": entries, "inputs_sha256": inputs_sha256,
    }
    if manifest["started_at"] is None:
        del manifest["started_at"]
    (set_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    return set_dir


def _manifest(set_dir: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((set_dir / "manifest.json").read_text("utf-8"))
    return data


def _frozen_sets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fingerprint: str, commit: bool = True
) -> tuple[Path, Path]:
    """A blind and an informed set inside the temporary repo, frozen, and (by default)
    committed with their records after the engine record."""
    root = tmp_path / "repo"
    blind = _set(root / GOV_REL, "g-blind", "blind", fingerprint)
    informed = _set(root / GOV_REL, "g-informed", "informed", fingerprint)
    _freeze_at(monkeypatch, "2026-11-10T11:00:00+00:00")
    freeze_set(blind)
    freeze_set(informed)
    if commit:
        _commit(root, "freeze the sets")
    return blind, informed


# --- the engine fingerprint --------------------------------------------------------------


def test_fingerprint_stable_and_changes_with_content(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    first = engine_fingerprint(root)
    assert len(first) == 64 and int(first, 16) >= 0
    assert engine_fingerprint(root) == first
    # Files outside tonomyx/ are not the engine.
    (root / "README.md").write_text("changed\n", encoding="utf-8")
    _commit(root, "readme")
    assert engine_fingerprint(root) == first
    # A content change, once committed, changes the fingerprint.
    (root / "tonomyx" / "core" / "rules.py").write_text("Y = 3\n", encoding="utf-8")
    _commit(root, "rules")
    changed = engine_fingerprint(root)
    assert changed != first
    # So does a rename with the same content, and a new file.
    _git(root, "mv", "tonomyx/engine.py", "tonomyx/engine2.py")
    _commit(root, "rename")
    assert engine_fingerprint(root) not in {first, changed}
    # Going back to the same content gives the same fingerprint.
    _git(root, "mv", "tonomyx/engine2.py", "tonomyx/engine.py")
    (root / "tonomyx" / "core" / "rules.py").write_text("Y = 2\n", encoding="utf-8")
    _commit(root, "back")
    assert engine_fingerprint(root) == first


def test_dirty_tree_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    rules = root / "tonomyx" / "core" / "rules.py"
    out = tmp_path / "engine.json"
    # An unstaged change.
    rules.write_text("Y = 3\n", encoding="utf-8")
    with pytest.raises(EngineDirty):
        engine_fingerprint(root)
    with pytest.raises(EngineDirty):
        freeze_engine(out, root=root)
    assert not out.exists()
    # A staged change.
    _git(root, "add", "tonomyx")
    with pytest.raises(EngineDirty):
        engine_fingerprint(root)
    _git(root, "commit", "-q", "-m", "rules")
    clean = engine_fingerprint(root)
    # An untracked file, even with untracked files hidden in the repo's config.
    _git(root, "config", "status.showUntrackedFiles", "no")
    (root / "tonomyx" / "extra.py").write_text("Z = 1\n", encoding="utf-8")
    with pytest.raises(EngineDirty):
        engine_fingerprint(root)
    (root / "tonomyx" / "extra.py").unlink()
    assert engine_fingerprint(root) == clean
    # A change hidden from git status by assume-unchanged or skip-worktree.
    for flag in ("--assume-unchanged", "--skip-worktree"):
        _git(root, "update-index", flag, "tonomyx/core/rules.py")
        with pytest.raises(EngineDirty):
            engine_fingerprint(root)
        _git(root, "update-index", flag.replace("--", "--no-"), "tonomyx/core/rules.py")
    assert engine_fingerprint(root) == clean
    # An ignored file, unless it is a bytecode cache.
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\n*.so\n", encoding="utf-8")
    _commit(root, "ignore")
    (root / "tonomyx" / "__pycache__").mkdir()
    (root / "tonomyx" / "__pycache__" / "engine.cpython-313.pyc").write_bytes(b"\0")
    assert engine_fingerprint(root) == clean
    (root / "tonomyx" / "native.so").write_bytes(b"\0")
    with pytest.raises(EngineDirty, match="ignored"):
        engine_fingerprint(root)
    (root / "tonomyx" / "native.so").unlink()
    # A change outside tonomyx/ is not the engine.
    (root / "README.md").write_text("dirty\n", encoding="utf-8")
    assert engine_fingerprint(root) == clean
    # No tracked engine at all is not an engine.
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init", "-q")
    with pytest.raises(EngineDirty):
        engine_fingerprint(empty)


def test_freeze_engine_writes_and_keeps_its_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, path, fingerprint = _engine(tmp_path, monkeypatch, commit=False)
    record = json.loads(path.read_text("utf-8"))
    head = _git(root, "rev-parse", "HEAD").strip()
    assert record == {"fingerprint": fingerprint, "commit": head, "frozen_at": ENGINE_AT,
                      "baselines": HEADS, "packages_sha256": PACKAGES}
    # Freezing the same engine again keeps the first record, so sets drafted after it stay
    # after it.
    _freeze_at(monkeypatch, AFTER)
    again = freeze_engine(path, root=root)
    assert (again.frozen_at, json.loads(path.read_text("utf-8"))) == (ENGINE_AT, record)
    # Another engine does not replace the record unless asked.
    (root / "tonomyx" / "engine.py").write_text("X = 2\n", encoding="utf-8")
    _commit(root, "engine")
    with pytest.raises(FreezeError, match="another engine"):
        freeze_engine(path, root=root)
    replaced = freeze_engine(path, root=root, replace=True)
    assert replaced.fingerprint != fingerprint and replaced.frozen_at == AFTER


# --- sets ----------------------------------------------------------------------------------


def test_set_change_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fingerprint = "a" * 64
    set_dir = _set(tmp_path, "g-blind", "blind", fingerprint)
    before = set_hash(set_dir)
    unfrozen = verify_set(set_dir)
    assert unfrozen.frozen_at is None and unfrozen.set_hash == before
    _freeze_at(monkeypatch, "2026-11-10T11:00:00+00:00")
    frozen = freeze_set(set_dir)
    assert (frozen.name, frozen.mode, frozen.set_hash) == ("g-blind", "blind", before)
    assert (frozen.engine_fingerprint, frozen.drafted_at) == (fingerprint, AFTER)
    assert frozen.frozen_at == "2026-11-10T11:00:00+00:00"
    manifest = _manifest(set_dir)
    assert manifest["frozen_at"] == frozen.frozen_at and manifest["set_hash"] == before
    assert verify_set(set_dir) == frozen
    # Freezing again changes nothing.
    _freeze_at(monkeypatch, "2026-11-12T00:00:00+00:00")
    assert freeze_set(set_dir) == frozen

    template = set_dir / "templates" / "procure_to_pay.json"
    original = template.read_bytes()

    def changed(edit: Any) -> None:
        saved = {p: p.read_bytes() for p in set_dir.rglob("*") if p.is_file()}
        edit()
        with pytest.raises(SetChanged):
            verify_set(set_dir)
        with pytest.raises(SetChanged):
            freeze_set(set_dir)
        for p in list(set_dir.rglob("*")):
            if p.is_file() and p not in saved:
                p.unlink()
        for p, data in saved.items():
            p.write_bytes(data)
        assert verify_set(set_dir) == frozen

    # A template edited, removed, or a template added.
    changed(lambda: template.write_bytes(original.replace(b"[]", b"[1]")))
    changed(lambda: template.unlink())
    changed(lambda: (set_dir / "templates" / "extra.json").write_text("{}", "utf-8"))
    changed(lambda: (set_dir / "templates" / "notes.txt").write_text("x", "utf-8"))

    # The manifest edited after the freeze: its own record no longer matches.
    def edit_manifest(key: str, value: Any) -> Any:
        def edit() -> None:
            m = _manifest(set_dir)
            m[key] = value
            (set_dir / "manifest.json").write_text(json.dumps(m), "utf-8")
        return edit

    changed(edit_manifest("drafted_at", "2026-11-11T00:00:00+00:00"))
    changed(edit_manifest("engine_fingerprint", "b" * 64))
    changed(edit_manifest("mode", "informed"))
    changed(edit_manifest("set_hash", "c" * 64))
    assert set_hash(set_dir) == before


def test_freeze_set_refuses_a_changed_or_empty_set(tmp_path: Path) -> None:
    set_dir = _set(tmp_path, "s", "blind", "a" * 64)
    (set_dir / "templates" / "order_to_cash.json").write_text("{}", "utf-8")
    with pytest.raises(SetChanged):
        freeze_set(set_dir)
    assert "frozen_at" not in _manifest(set_dir)
    empty = _set(tmp_path, "e", "blind", "a" * 64, processes=())
    with pytest.raises(FreezeError, match="no template"):
        freeze_set(empty)
    odd = _set(tmp_path, "o", "other", "a" * 64)
    with pytest.raises(SetChanged, match="mode"):
        verify_set(odd)
    with pytest.raises(SetChanged, match="manifest"):
        verify_set(tmp_path / "missing")


def test_freeze_set_reads_what_draft_set_writes(tmp_path: Path) -> None:
    from tests.drafting.test_draft import BRIEF, IDENT, Fake, good_template
    from tonomyx.drafting.draft import draft_set

    draft_set("g-blind", "blind", [BRIEF], {}, Fake([good_template()]), tmp_path / "set",
              seed=0, engine_fingerprint="d" * 64, identity=IDENT)
    frozen = freeze_set(tmp_path / "set")
    assert (frozen.name, frozen.mode, frozen.engine_fingerprint) == (
        "g-blind", "blind", "d" * 64)
    assert frozen.frozen_at is not None and frozen.set_hash == set_hash(tmp_path / "set")


# --- the unlock ----------------------------------------------------------------------------


def test_unlock_allowed_records_the_set_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    blind, informed = _frozen_sets(tmp_path, monkeypatch, fingerprint)
    unlock = unlock_paper(engine, [blind, informed], root=root)
    assert is_issued(unlock)
    assert unlock.engine.fingerprint == fingerprint and unlock.engine.frozen_at == ENGINE_AT
    assert unlock.set_hashes == {"g-blind": set_hash(blind), "g-informed": set_hash(informed)}
    assert [s.mode for s in unlock.sets] == ["blind", "informed"]


def test_unlock_requires_engine_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    sets = _frozen_sets(tmp_path, monkeypatch, fingerprint)
    rules = root / "tonomyx" / "core" / "rules.py"
    # Dirty.
    rules.write_text("Y = 3\n", encoding="utf-8")
    with pytest.raises(UnlockRefused, match="uncommitted"):
        unlock_paper(engine, sets, root=root)
    # Committed, so clean, but another engine.
    _commit(root, "rules")
    with pytest.raises(UnlockRefused, match="fingerprint"):
        unlock_paper(engine, sets, root=root)
    # Back to the frozen content: allowed again.
    rules.write_text("Y = 2\n", encoding="utf-8")
    _commit(root, "back")
    assert is_issued(unlock_paper(engine, sets, root=root))
    # No engine freeze, or a broken one.
    with pytest.raises(UnlockRefused, match="engine freeze"):
        unlock_paper(tmp_path / "none.json", sets, root=root)
    engine.write_text(json.dumps({"fingerprint": fingerprint, "commit": "x"}), "utf-8")
    with pytest.raises(UnlockRefused, match="engine freeze"):
        unlock_paper(engine, sets, root=root)


def test_unlock_requires_set_drafted_after_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    blind, informed = _frozen_sets(tmp_path, monkeypatch, fingerprint)
    _freeze_at(monkeypatch, "2026-11-10T11:00:00+00:00")
    # Drafted before the engine freeze, or in the same second.
    for i, when in enumerate((BEFORE, ENGINE_AT)):
        early = _set(tmp_path / "early", f"early{i}", "blind", fingerprint, drafted_at=when,
                     started_at=when)
        freeze_set(early)
        with pytest.raises(UnlockRefused, match="drafted"):
            unlock_paper(engine, [early, informed], root=root)
    # Drafted on another engine, or on no frozen engine.
    for i, other in enumerate(("b" * 64, "dev", "unfrozen")):
        stray = _set(tmp_path / "stray", f"stray{i}", "informed", other)
        freeze_set(stray)
        with pytest.raises(UnlockRefused, match="engine"):
            unlock_paper(engine, [blind, stray], root=root)
    # Not frozen.
    loose = _set(tmp_path / "loose", "loose", "informed", fingerprint)
    with pytest.raises(UnlockRefused, match="not frozen"):
        unlock_paper(engine, [blind, loose], root=root)
    # Frozen, then changed.
    (informed / "templates" / "order_to_cash.json").write_text("{}", "utf-8")
    with pytest.raises(UnlockRefused, match="changed"):
        unlock_paper(engine, [blind, informed], root=root)


def test_unlock_requires_blind_and_informed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    blind, informed = _frozen_sets(tmp_path, monkeypatch, fingerprint)
    blind2 = _set(root / GOV_REL, "g-blind-2", "blind", fingerprint)
    freeze_set(blind2)
    _commit(root, "freeze another blind set")
    for sets in ([blind], [informed], [blind, blind2], []):
        with pytest.raises(UnlockRefused, match="blind and one informed"):
            unlock_paper(engine, sets, root=root)
    # Two sets of one name would be recorded under one name; freeze_set never freezes a
    # second set under a name already frozen.
    with pytest.raises(UnlockRefused, match="name"):
        unlock_paper(engine, [blind, blind, informed], root=root)
    twin = _set(tmp_path / "twin", "g-blind", "informed", fingerprint)
    with pytest.raises(FreezeError, match="already frozen"):
        freeze_set(twin)
    assert is_issued(unlock_paper(engine, [blind, blind2, informed], root=root))


def test_unlock_cannot_be_constructed_directly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(TypeError):
        EvaluationUnlock()  # type: ignore[call-arg]
    engine = freeze.EngineFreeze("a" * 64, "c", ENGINE_AT)
    with pytest.raises(TypeError, match="unlock_paper"):
        EvaluationUnlock(object(), engine, (), ENGINE_AT)
    # Built around the constructor: never issued, so never accepted.
    forged = object.__new__(EvaluationUnlock)
    assert not is_issued(forged)
    # Even with the private sentinel, only unlock_paper issues one.
    assert not is_issued(EvaluationUnlock(freeze._SENTINEL, engine, (), ENGINE_AT))
    with pytest.raises(TypeError):

        class Sub(EvaluationUnlock):  # type: ignore[misc]  # noqa: F841
            pass

    root, path, fingerprint = _engine(tmp_path, monkeypatch)
    real = unlock_paper(path, _frozen_sets(tmp_path, monkeypatch, fingerprint), root=root)
    with pytest.raises(AttributeError):
        real.sets = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        del real.sets
    with pytest.raises(AttributeError):
        object.__setattr__(real, "_extra", 1)
    with pytest.raises(TypeError):
        pickle.dumps(real)
    # A copy is the same unlock, not a new one.
    assert copy.copy(real) is real and copy.deepcopy(real) is real


# --- answer_side ---------------------------------------------------------------------------


def _paper_case(root: Path, industry: str = "ban_le") -> Path:
    """A temporary case folder of a paper industry with synthetic content."""
    case = root / "CASE-SYNTH-01"
    (case / "expected" / "final_state").mkdir(parents=True)
    (case / "data").mkdir()
    meta = {"case_id": "CASE-SYNTH-01", "title": "Hồ sơ tổng hợp", "industry": industry}
    (case / "case.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (case / "roles.csv").write_text(
        "ma_vai,loai,soan_bang,yeu_cau_duyet,duyet_loai\nDP-01,dieu_phoi,,,\n", "utf-8"
    )
    (case / "process.json").write_text(json.dumps({"start": "S00", "steps": []}), "utf-8")
    (case / "attacks.json").write_text(json.dumps([{"id": "A1"}]), "utf-8")
    (case / "story.md").write_text("synthetic\n", "utf-8")
    exp = case / "expected"
    (exp / "outcome.json").write_text(json.dumps({"stop": {"type": "end"}}), "utf-8")
    (exp / "invariants.json").write_text(json.dumps({"invariants": ["I1"]}), "utf-8")
    (exp / "events.csv").write_text("kind,ref\nDRAFTED,X1\n", "utf-8")
    (exp / "final_state" / "chung_tu.csv").write_text("so_ct,loai_ct\nX1,don_mua\n", "utf-8")
    (case / "data" / "chung_tu.csv").write_text("so_ct,loai_ct\nX0,don_mua\n", "utf-8")
    return case


_OPENED: list[str] | None = None


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if _OPENED is not None and event == "open" and isinstance(args[0], str | Path):
        _OPENED.append(str(args[0]))


sys.addaudithook(_audit)


@pytest.fixture
def opened() -> Iterator[list[str]]:
    """Every file path opened while the test runs (the interpreter's audit hook)."""
    global _OPENED
    _OPENED = []
    try:
        yield _OPENED
    finally:
        _OPENED = None


@pytest.mark.parametrize("industry", PAPER_INDUSTRIES)
def test_answer_side_refuses_paper_without_unlock(
    tmp_path: Path, industry: str, opened: list[str]
) -> None:
    case = _paper_case(tmp_path, industry)
    opened.clear()  # the files written above
    with pytest.raises(PaperCaseRefused) as refused:
        answer_side(case)
    assert str(refused.value) == (
        f"CASE-SYNTH-01: {industry} is a paper industry; its answers are not read"
    )
    # Something that only looks like an unlock is refused the same way.
    forged = object.__new__(EvaluationUnlock)
    for fake in (forged, object(), True):
        with pytest.raises(PaperCaseRefused, match="not read"):
            answer_side(case, unlock=fake)  # type: ignore[arg-type]
    inside = [p for p in opened if p.startswith(str(case))]
    assert inside and set(inside) == {str(case / "case.meta.json")}


def test_answer_side_with_unlock_reads_a_temp_paper_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    unlock = unlock_paper(engine, _frozen_sets(tmp_path, monkeypatch, fingerprint), root=root)
    case = _paper_case(tmp_path / "cases")
    answer = answer_side(case, unlock=unlock)
    assert (answer.case_id, answer.industry) == ("CASE-SYNTH-01", "ban_le")
    assert answer.process["start"] == "S00" and answer.attacks == [{"id": "A1"}]
    assert answer.outcome["stop"]["type"] == "end"
    assert answer.final_state["chung_tu"][0]["so_ct"] == "X1"
    assert answer.given["chung_tu"][0]["so_ct"] == "X0"
    # The unlock opens the paper industries only, never a case of no known industry.
    for industry in ("", "thuong_mai"):
        odd = _paper_case(tmp_path / f"odd{industry}", industry)
        with pytest.raises(PaperCaseRefused, match="not a development industry"):
            answer_side(odd, unlock=unlock)


# --- the CLI -------------------------------------------------------------------------------


def test_cli_freeze_engine_and_set_print_hashes_and_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import aebench.cli as cli

    root = _repo(tmp_path)
    monkeypatch.setattr(cli, "REPO_ROOT", root)
    out = tmp_path / "freeze" / "engine.json"
    assert cli.main(["freeze", "engine", "--out", str(out)]) == 0
    fingerprint = engine_fingerprint(root)
    printed = capsys.readouterr().out.split()
    assert f"fingerprint={fingerprint}" in printed and f"path={out}" in printed
    set_dir = _set(tmp_path, "g-blind", "blind", fingerprint)
    entries = _manifest(set_dir)
    entries["processes"]["order_to_cash"]["status"] = "invalid"
    (set_dir / "manifest.json").write_text(json.dumps(entries), "utf-8")
    assert cli.main(["freeze", "set", str(set_dir)]) == 0
    printed = capsys.readouterr().out.split()
    assert f"set_hash={set_hash(set_dir)}" in printed and f"path={set_dir}" in printed
    # Task 10 N4: how many of the set's processes drafted a valid template.
    assert "valid=1" in printed and "total=2" in printed
    # Refusals print a count or a reason, never file content, and exit non-zero.
    (set_dir / "templates" / "procure_to_pay.json").write_text("{}", "utf-8")
    assert cli.main(["freeze", "set", str(set_dir)]) == 2
    assert capsys.readouterr().out.startswith("refused:")
    (root / "tonomyx" / "engine.py").write_text("X = 9\n", encoding="utf-8")
    assert cli.main(["freeze", "engine", "--out", str(tmp_path / "e2.json")]) == 2
    assert capsys.readouterr().out.startswith("refused:")


def _draft_args(tmp_path: Path, *industries: str) -> list[str]:
    return ["draft", "--mode", "blind", "--industries", *industries, "--name", "g",
            "--out", str(tmp_path / "out")]


def _cli_draft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dirty: bool) -> Any:
    import aebench.cli as cli
    from tests.drafting.test_draft import _Hosted, good_template
    from tests.drafting.test_sources import make_bench

    (tmp_path / "bench").mkdir()
    root = make_bench(tmp_path / "bench", {"C1": "ban_le", "C2": "san_xuat"})
    monkeypatch.setattr(cli, "BENCH_ROOT", root)

    def fingerprint() -> str:
        if dirty:
            raise EngineDirty("tonomyx/ has uncommitted changes (1 paths)")
        return "e" * 64

    monkeypatch.setattr(cli, "engine_fingerprint", fingerprint)
    monkeypatch.setattr(cli, "create_json_model", lambda name, **k: _Hosted([good_template()]))
    return cli


def test_cli_draft_refuses_paper_on_a_dirty_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _cli_draft(tmp_path, monkeypatch, dirty=True)
    for industries in (["ban_le"], ["san_xuat", "ban_le"], ["thuong_mai"]):
        assert cli.main(_draft_args(tmp_path, *industries)) == 2
        assert capsys.readouterr().out.startswith("refused:")
        assert not (tmp_path / "out").exists()


def test_cli_draft_dev_on_a_dirty_engine_is_marked_dev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _cli_draft(tmp_path, monkeypatch, dirty=True)
    cli.main(_draft_args(tmp_path, "san_xuat"))
    assert "note: tonomyx/ has uncommitted changes" in capsys.readouterr().out
    assert _manifest(tmp_path / "out")["engine_fingerprint"] == "dev"


def test_cli_draft_records_the_engine_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _cli_draft(tmp_path, monkeypatch, dirty=False)
    cli.main(_draft_args(tmp_path, "ban_le"))
    assert f"engine_fingerprint={'e' * 64}" in capsys.readouterr().out.split()
    assert _manifest(tmp_path / "out")["engine_fingerprint"] == "e" * 64
    # A frozen set is never drafted over.
    freeze_set(tmp_path / "out")
    frozen = (tmp_path / "out" / "manifest.json").read_bytes()
    assert cli.main(_draft_args(tmp_path, "ban_le")) == 2
    assert capsys.readouterr().out.startswith("refused:")
    assert (tmp_path / "out" / "manifest.json").read_bytes() == frozen


# --- fix round 1 ---------------------------------------------------------------------------


def test_symlinks_in_the_engine_refused(tmp_path: Path) -> None:
    """I1: a symlink's behaviour is not in its target string."""
    makers: list[Callable[[Path], None]] = [
        lambda root: (root / "tonomyx" / "link.py").symlink_to("engine.py"),
        lambda root: (root / "tonomyx" / "linked").symlink_to(root / "tonomyx" / "core"),
        lambda root: (root / "aebench" / "arms" / "g2.py").symlink_to("guards.py"),
    ]
    for n, make in enumerate(makers):
        root = _repo(tmp_path / str(n))
        make(root)
        _commit(root, "symlink")  # committed, so git status is clean
        with pytest.raises(EngineDirty, match="mode 120000"):
            engine_fingerprint(root)
    # The engine folder itself a symlink to a clean copy.
    root = _repo(tmp_path / "whole")
    real = tmp_path / "elsewhere"
    (root / "tonomyx").rename(real)
    (root / "tonomyx").symlink_to(real)
    with pytest.raises(EngineDirty):
        engine_fingerprint(root)


def test_fingerprint_covers_aebench_but_not_analysis_or_report(tmp_path: Path) -> None:
    """R10d."""
    root = _repo(tmp_path)
    clean = engine_fingerprint(root)
    for rel in ("aebench/analysis/stats.py", "aebench/report/r.py"):
        (root / rel).write_text("Z = 2\n", encoding="utf-8")  # dirty, but not the engine
        (root / rel).with_name("new.py").write_text("W = 1\n", encoding="utf-8")
        (root / rel).with_name("link.py").symlink_to("new.py")
        assert engine_fingerprint(root) == clean
        _commit(root, rel)
        assert engine_fingerprint(root) == clean
    guards = root / "aebench" / "arms" / "guards.py"
    guards.write_text("Z = 2\n", encoding="utf-8")
    with pytest.raises(EngineDirty, match="uncommitted"):
        engine_fingerprint(root)
    _commit(root, "guards")
    assert engine_fingerprint(root) != clean
    (root / "aebench" / "runner.py").write_text("R = 1\n", encoding="utf-8")
    with pytest.raises(EngineDirty, match="uncommitted"):
        engine_fingerprint(root)


def test_root_must_be_the_top_of_its_work_tree(tmp_path: Path) -> None:
    """R10c.1: a repo-local core.worktree, or a subfolder as root, is refused."""
    root = _repo(tmp_path)
    with pytest.raises(EngineDirty, match="top of its git work tree"):
        engine_fingerprint(root / "tonomyx")
    other = _repo(tmp_path / "other")
    _git(root, "config", "core.worktree", str(other))
    with pytest.raises(EngineDirty, match="top of its git work tree"):
        engine_fingerprint(root)


def test_engine_record_commit_checked_and_replace_keeps_a_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R10c.2."""
    root = _repo(tmp_path)
    first = _git(root, "rev-parse", "HEAD").strip()
    (root / "tonomyx" / "engine.py").write_text("X = 2\n", encoding="utf-8")
    _commit(root, "engine 2")
    root_head = _git(root, "rev-parse", "HEAD").strip()
    (root / "README.md").write_text("docs\n", encoding="utf-8")
    _commit(root, "docs")
    # A commit on a side branch, not an ancestor of HEAD.
    _git(root, "checkout", "-q", "-b", "side", first)
    (root / "README.md").write_text("side\n", encoding="utf-8")
    _commit(root, "side")
    side = _git(root, "rev-parse", "HEAD").strip()
    _git(root, "checkout", "-q", "-")
    _freeze_at(monkeypatch, ENGINE_AT)
    path = root / FREEZE_REL / "engine.json"
    freeze_engine(path, root=root)
    record = json.loads(path.read_text("utf-8"))
    # An older commit whose engine tree equals HEAD's is still the frozen engine.
    record["commit"] = root_head
    path.write_text(json.dumps(record), "utf-8")
    _commit(root, "freeze the engine")
    sets = _frozen_sets(tmp_path, monkeypatch, record["fingerprint"])
    assert is_issued(unlock_paper(path, sets, root=root))
    for commit, why in ((first, "differs"), (side, "not an ancestor"),
                        ("0" * 40, "does not have"), ("--all", "no commit")):
        record["commit"] = commit
        path.write_text(json.dumps(record), "utf-8")
        with pytest.raises(UnlockRefused, match=why):
            unlock_paper(path, sets, root=root)
    record["commit"] = root_head
    path.write_text(json.dumps(record), "utf-8")
    old = path.read_bytes()
    # --replace keeps each old record as a timestamped copy and never overwrites one.
    for n, content in enumerate(("X = 3\n", "X = 4\n")):
        (root / "tonomyx" / "engine.py").write_text(content, encoding="utf-8")
        _commit(root, content)
        _freeze_at(monkeypatch, f"2026-11-1{n + 1}T00:00:00+00:00")
        freeze_engine(path, root=root, replace=True)
    copies = sorted(p.name for p in path.parent.glob("engine.*.json"))
    assert copies == ["engine.20261110T0900000000.json", "engine.20261111T0000000000.json"]
    assert (path.parent / copies[0]).read_bytes() == old


def test_unlock_requires_drafting_started_after_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R10a."""
    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    blind, informed = _frozen_sets(tmp_path, monkeypatch, fingerprint)
    started_early = _set(tmp_path / "x", "early", "informed", fingerprint, started_at=BEFORE)
    freeze_set(started_early)
    with pytest.raises(UnlockRefused, match="drafted before"):
        unlock_paper(engine, [blind, started_early], root=root)
    unrecorded = _set(tmp_path / "x", "unrecorded", "informed", fingerprint, started_at=None)
    freeze_set(unrecorded)
    with pytest.raises(UnlockRefused, match="started"):
        unlock_paper(engine, [blind, unrecorded], root=root)


def test_draft_set_records_started_at_before_the_first_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R10a: started_at is taken before the first model call, drafted_at after the last."""
    from tests.drafting.test_draft import BRIEF, IDENT, Fake, good_template
    from tonomyx.drafting import draft

    times = ["2026-11-10T09:00:01+00:00", "2026-11-10T09:00:09+00:00"]
    read: list[str] = []

    class Clock:
        @staticmethod
        def now(tz: Any) -> Any:
            from datetime import datetime

            read.append(times[len(read)])
            return datetime.fromisoformat(read[-1])

    class Watched(Fake):
        def complete_json(self, system: str, user: str, *, seed: int) -> Any:
            assert read == times[:1]  # the start was taken, the end not yet
            return super().complete_json(system, user, seed=seed)

    monkeypatch.setattr(draft, "datetime", Clock)
    draft.draft_set("g", "blind", [BRIEF], {}, Watched([good_template()]), tmp_path / "set",
                    seed=0, engine_fingerprint="d" * 64, identity=IDENT)
    manifest = _manifest(tmp_path / "set")
    # Microseconds (Task 10 N1).
    assert manifest["started_at"] == "2026-11-10T09:00:01.000000+00:00"
    assert manifest["drafted_at"] == "2026-11-10T09:00:09.000000+00:00"
    assert freeze_set(tmp_path / "set").started_at == manifest["started_at"]


def test_unlock_requires_the_separate_set_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R10c.3: a set edited with its manifest rewritten to match is still caught."""
    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    blind, informed = _frozen_sets(tmp_path, monkeypatch, fingerprint)
    record_path = root / FREEZE_REL / "sets" / "g-informed.json"
    record = json.loads(record_path.read_text("utf-8"))
    assert record == {"set_hash": set_hash(informed), "mode": "informed",
                      "frozen_at": "2026-11-10T11:00:00+00:00"}
    # Forge: change a template and rewrite every hash in the manifest consistently.
    template = informed / "templates" / "order_to_cash.json"
    template.write_text(json.dumps({"id": "order_to_cash", "steps": ["x"]}), "utf-8")
    manifest = _manifest(informed)
    manifest["processes"]["order_to_cash"]["sha256"] = freeze._sha(template)
    manifest["set_hash"] = set_hash(informed)
    manifest["frozen_manifest_sha256"] = freeze._manifest_digest(manifest)
    (informed / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    assert verify_set(informed).set_hash == set_hash(informed)  # the manifest alone agrees
    with pytest.raises(UnlockRefused, match="freeze record"):
        unlock_paper(engine, [blind, informed], root=root)
    with pytest.raises(SetChanged, match="freeze record"):
        freeze_set(informed)
    # No record at all.
    (root / FREEZE_REL / "sets" / "g-blind.json").unlink()
    with pytest.raises(UnlockRefused, match="no readable freeze record"):
        unlock_paper(engine, [blind, informed], root=root)


def test_symlinked_templates_or_manifest_refused(tmp_path: Path) -> None:
    """R10c.4."""
    set_dir = _set(tmp_path, "s", "blind", "a" * 64)
    real = tmp_path / "real-templates"
    (set_dir / "templates").rename(real)
    (set_dir / "templates").symlink_to(real)
    with pytest.raises(SetChanged, match="templates/ is a symlink"):
        verify_set(set_dir)
    with pytest.raises(SetChanged, match="templates/ is a symlink"):
        freeze_set(set_dir)
    other = _set(tmp_path, "m", "blind", "a" * 64)
    (other / "manifest.json").rename(tmp_path / "m.json")
    (other / "manifest.json").symlink_to(tmp_path / "m.json")
    with pytest.raises(SetChanged, match="manifest.json is a symlink"):
        verify_set(other)


def test_cli_draft_refuses_when_the_engine_changes_during_drafting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R10c.5."""
    cli = _cli_draft(tmp_path, monkeypatch, dirty=False)
    answers = iter(["e" * 64, "f" * 64])
    monkeypatch.setattr(cli, "engine_fingerprint", lambda: next(answers))
    assert cli.main(_draft_args(tmp_path, "ban_le")) == 2
    assert capsys.readouterr().out.splitlines()[-1].startswith("refused: the engine changed")
    manifest = _manifest(tmp_path / "out")
    assert manifest["invalid"] and manifest["engine_fingerprint"] == "invalid"
    with pytest.raises(SetChanged, match="invalid"):
        freeze_set(tmp_path / "out")
    # An engine that became unclean during drafting is a change too.
    def dirty_after() -> str:
        if calls.pop(0):
            raise EngineDirty("the engine has uncommitted changes (1 paths)")
        return "e" * 64

    calls = [False, True]
    monkeypatch.setattr(cli, "engine_fingerprint", dirty_after)
    out2 = tmp_path / "out2"
    argv = _draft_args(tmp_path, "ban_le")
    argv[argv.index(str(tmp_path / "out"))] = str(out2)
    assert cli.main(argv) == 2
    assert _manifest(out2)["engine_fingerprint"] == "invalid"


# --- final review I6, I7 and Task 10 N1, N2 -------------------------------------------------


def test_unlock_requires_the_inputs_the_sets_were_drafted_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I6: the reviewed inputs file is part of the freeze."""
    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    blind, informed = _frozen_sets(tmp_path, monkeypatch, fingerprint)
    unlock = unlock_paper(engine, [blind, informed], root=root)
    assert unlock.inputs_sha256 == INPUTS_SHA
    # A set that records no inputs file, or another one.
    for i, recorded in enumerate((None, "f" * 64)):
        other = _set(root / GOV_REL, f"g-other{i}", "informed", fingerprint,
                     inputs_sha256=recorded)
        freeze_set(other)
        _commit(root, f"other {i}")
        why = "does not record the inputs" if recorded is None else "different inputs"
        with pytest.raises(UnlockRefused, match=why):
            unlock_paper(engine, [blind, informed, other], root=root)
    # The inputs file changed since the sets were drafted, committed or not.
    inputs = root / freeze.INPUTS_REL
    inputs.write_text('{"version": 1, "cases": {"X": {}}}\n', encoding="utf-8")
    with pytest.raises(UnlockRefused, match="inputs file changed"):
        unlock_paper(engine, [blind, informed], root=root)
    _commit(root, "inputs edited after drafting")
    with pytest.raises(UnlockRefused, match="inputs file changed"):
        unlock_paper(engine, [blind, informed], root=root)
    inputs.unlink()
    with pytest.raises(UnlockRefused, match="no readable inputs file"):
        unlock_paper(engine, [blind, informed], root=root)


def test_unlock_requires_freeze_files_committed_and_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I7 (a): the freeze rests on git, so every freeze file is committed and unchanged."""
    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    blind, informed = _frozen_sets(tmp_path, monkeypatch, fingerprint)
    assert is_issued(unlock_paper(engine, [blind, informed], root=root))
    # A frozen set that is not committed.
    loose = _set(root / GOV_REL, "g-loose", "informed", fingerprint)
    freeze_set(loose)
    with pytest.raises(UnlockRefused, match="not committed"):
        unlock_paper(engine, [blind, loose], root=root)
    # The engine record rewritten with the same values (so it reads the same), on disk...
    original = engine.read_text("utf-8")
    engine.write_text(json.dumps(json.loads(original)), "utf-8")
    with pytest.raises(UnlockRefused, match="changed since HEAD"):
        unlock_paper(engine, [blind, informed], root=root)
    # ...hidden from git status by assume-unchanged...
    rel = f"{FREEZE_REL}/engine.json"
    _git(root, "update-index", "--assume-unchanged", rel)
    with pytest.raises(UnlockRefused, match="changed since HEAD"):
        unlock_paper(engine, [blind, informed], root=root)
    _git(root, "update-index", "--no-assume-unchanged", rel)
    # ...or staged while the disk shows the committed text.
    _git(root, "add", rel)
    engine.write_text(original, "utf-8")
    with pytest.raises(UnlockRefused, match="staged"):
        unlock_paper(engine, [blind, informed], root=root)
    _git(root, "add", rel)
    assert is_issued(unlock_paper(engine, [blind, informed], root=root))
    # An engine record outside the repository (with a copy of the set records beside it).
    outside = tmp_path / "outside"
    shutil.copytree(root / FREEZE_REL, outside)
    with pytest.raises(UnlockRefused, match="outside the repository"):
        unlock_paper(outside / "engine.json", [blind, informed], root=root)
    # A set outside the repository.
    away = _set(tmp_path / "away", "g-away", "informed", fingerprint)
    freeze_set(away)
    _commit(root, "the away set's record")
    with pytest.raises(UnlockRefused, match="outside the repository"):
        unlock_paper(engine, [blind, away], root=root)


def test_unlock_requires_the_engine_record_committed_before_the_sets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I7 (b): every commit that touched the engine record is a strict ancestor of every
    commit that added a set record, whatever the timestamps say."""
    # In one commit with the set records.
    monkeypatch.setattr(freeze, "FREEZE_DIR", tmp_path / "same" / "repo" / FREEZE_REL)
    root, engine, fingerprint = _engine(tmp_path / "same", monkeypatch, commit=False)
    sets = _frozen_sets(tmp_path / "same", monkeypatch, fingerprint)
    with pytest.raises(UnlockRefused, match="before or with the engine record"):
        unlock_paper(engine, sets, root=root)
    # The set records committed first, the engine record after.
    monkeypatch.setattr(freeze, "FREEZE_DIR", tmp_path / "late" / "repo" / FREEZE_REL)
    root, engine, fingerprint = _engine(tmp_path / "late", monkeypatch, commit=False)
    sets = _frozen_sets(tmp_path / "late", monkeypatch, fingerprint, commit=False)
    _git(root, "add", GOV_REL, f"{FREEZE_REL}/sets")
    _git(root, "commit", "-q", "-m", "sets first")
    _commit(root, "engine after")
    with pytest.raises(UnlockRefused, match="before or with the engine record"):
        unlock_paper(engine, sets, root=root)
    # The engine record edited (say, its frozen_at moved back) after the sets were frozen.
    monkeypatch.setattr(freeze, "FREEZE_DIR", tmp_path / "edit" / "repo" / FREEZE_REL)
    root, engine, fingerprint = _engine(tmp_path / "edit", monkeypatch)
    sets = _frozen_sets(tmp_path / "edit", monkeypatch, fingerprint)
    assert is_issued(unlock_paper(engine, sets, root=root))
    record = json.loads(engine.read_text("utf-8"))
    engine.write_text(json.dumps({**record, "frozen_at": BEFORE}, indent=1), "utf-8")
    _commit(root, "engine record edited")
    with pytest.raises(UnlockRefused, match="before or with the engine record"):
        unlock_paper(engine, sets, root=root)


def test_freeze_times_carry_microseconds() -> None:
    """Task 10 N1: a fast legitimate flow is never refused for being in the same second."""
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00", freeze._now())


def test_a_case_insensitive_repo_config_hides_nothing(tmp_path: Path) -> None:
    """Task 10 N2: a repo-local core.ignorecase=true would hide tonomyx/Engine.py beside
    the tracked tonomyx/engine.py; the checks run with core.ignorecase=false."""
    root = _repo(tmp_path)
    clean = engine_fingerprint(root)
    _git(root, "config", "core.ignorecase", "true")
    (root / "tonomyx" / "Engine.py").write_text("X = 9\n", encoding="utf-8")
    with pytest.raises(EngineDirty, match="uncommitted"):
        engine_fingerprint(root)
    (root / "tonomyx" / "Engine.py").unlink()
    assert engine_fingerprint(root) == clean


# --- final ruling I3: tracked baseline folders, vendored clones, installed packages ---------


def test_fingerprint_covers_the_tracked_baseline_folders(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    for rel in ("baselines/nemo_config/config.yml", "baselines/llama_guard_format/f.py",
                "baselines/README.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("a\n", encoding="utf-8")
    _commit(root, "baselines")
    clean = engine_fingerprint(root)
    for rel in ("baselines/nemo_config/config.yml", "baselines/llama_guard_format/f.py"):
        (root / rel).write_text("b\n", encoding="utf-8")
        with pytest.raises(EngineDirty, match="uncommitted"):
            engine_fingerprint(root)
        _commit(root, rel)
        changed = engine_fingerprint(root)
        assert changed != clean
        clean = changed
    # The README beside them is documentation, not the engine.
    (root / "baselines/README.md").write_text("b\n", encoding="utf-8")
    assert engine_fingerprint(root) == clean
    (root / "baselines/nemo_config/rails.co").write_text("x\n", encoding="utf-8")
    with pytest.raises(EngineDirty, match="uncommitted"):
        engine_fingerprint(root)


def test_freeze_engine_refuses_a_dirty_or_missing_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, environment: dict[str, Any]
) -> None:
    root = _repo(tmp_path)
    out = tmp_path / "engine.json"
    environment["heads"]["camel"]["clean"] = False
    with pytest.raises(EngineDirty, match="camel"):
        freeze_engine(out, root=root)
    environment["heads"]["camel"] = {"head": None, "clean": False}
    with pytest.raises(EngineDirty, match="camel"):
        freeze_engine(out, root=root)
    assert not out.exists()


def test_freeze_engine_again_with_other_clones_or_packages_needs_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, environment: dict[str, Any]
) -> None:
    root, path, _ = _engine(tmp_path, monkeypatch, commit=False)
    environment["packages"] = "c" * 64
    with pytest.raises(FreezeError, match="another engine"):
        freeze_engine(path, root=root)
    assert freeze_engine(path, root=root, replace=True).packages_sha256 == "c" * 64


def test_unlock_refuses_other_clones_or_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, environment: dict[str, Any]
) -> None:
    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    sets = _frozen_sets(tmp_path, monkeypatch, fingerprint)
    assert is_issued(unlock_paper(engine, sets, root=root))
    environment["heads"]["progent"]["head"] = "d" * 40
    with pytest.raises(UnlockRefused, match="progent"):
        unlock_paper(engine, sets, root=root)
    environment["heads"]["progent"] = dict(HEADS["progent"], clean=False)
    with pytest.raises(UnlockRefused, match="progent"):
        unlock_paper(engine, sets, root=root)
    environment["heads"] = copy.deepcopy(HEADS)
    environment["packages"] = "e" * 64
    with pytest.raises(UnlockRefused, match="packages"):
        unlock_paper(engine, sets, root=root)
    environment["packages"] = PACKAGES
    assert is_issued(unlock_paper(engine, sets, root=root))


def test_unlock_refuses_an_engine_record_without_clones_or_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, engine, _ = _engine(tmp_path, monkeypatch, commit=False)
    record = json.loads(engine.read_text("utf-8"))
    for key in ("baselines", "packages_sha256"):
        engine.write_text(json.dumps({k: v for k, v in record.items() if k != key}), "utf-8")
        with pytest.raises(UnlockRefused, match="records no"):
            unlock_paper(engine, [], root=root)
    for bad in ({"baselines": {"camel": "x"}}, {"packages_sha256": "nope"}):
        engine.write_text(json.dumps({**record, **bad}), "utf-8")
        with pytest.raises(FreezeError, match="engine freeze"):
            freeze.read_engine_freeze(engine)


def test_paper_freeze_ok_rechecks_clones_and_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, environment: dict[str, Any]
) -> None:
    from aebench.run import experiment as experiment_module

    root, engine, fingerprint = _engine(tmp_path, monkeypatch)
    sets = _frozen_sets(tmp_path, monkeypatch, fingerprint)
    unlock = unlock_paper(engine, sets, root=root)
    monkeypatch.setattr(experiment_module, "engine_fingerprint", lambda: fingerprint)
    inputs = root / freeze.INPUTS_REL
    assert experiment_module.paper_freeze_ok(unlock, [], inputs)
    environment["heads"]["agentdojo"]["clean"] = False
    assert not experiment_module.paper_freeze_ok(unlock, [], inputs)
    environment["heads"] = copy.deepcopy(HEADS)
    environment["packages"] = "f" * 64
    assert not experiment_module.paper_freeze_ok(unlock, [], inputs)


def _clone(path: Path, *, commit: bool = True) -> str:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    (path / "x.py").write_text("X = 1\n", encoding="utf-8")
    if commit:
        _commit(path, "x")
        return _git(path, "rev-parse", "HEAD").strip()
    return ""


def test_baseline_heads_reads_each_clone_with_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # the real reader
    root = _repo(tmp_path)
    head = _clone(root / "baselines" / "agentdojo")
    dirty = _clone(root / "baselines" / "camel")
    (root / "baselines" / "camel" / "x.py").write_text("X = 2\n", encoding="utf-8")
    untracked = _clone(root / "baselines" / "progent")
    (root / "baselines" / "progent" / "new.py").write_text("N = 1\n", encoding="utf-8")
    # A folder that is no repository of its own would report the parent repo's HEAD.
    (root / "baselines" / "purple_llama").mkdir()
    heads = freeze.baseline_heads(root)
    assert heads == {
        "agentdojo": {"head": head, "clean": True},
        "camel": {"head": dirty, "clean": False},
        "nemo_guardrails": {"head": None, "clean": False},
        "purple_llama": {"head": None, "clean": False},
        "progent": {"head": untracked, "clean": False},
    }


def test_packages_sha256_hashes_installed_distributions_but_the_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.undo()

    class Dist:
        def __init__(self, name: str | None, version: str) -> None:
            self.metadata = {"Name": name} if name is not None else {}
            self.version = version

    def fake(*dists: Dist) -> None:
        monkeypatch.setattr(freeze.importlib.metadata, "distributions", lambda: list(dists))

    fake(Dist("Torch", "2.15.0"), Dist("aebench", "0.1"), Dist("z3_solver", "4.15"))
    first = freeze.packages_sha256()
    expected = hashlib.sha256(b"torch==2.15.0\nz3-solver==4.15").hexdigest()
    assert first == expected
    fake(Dist("z3-solver", "4.15"), Dist("torch", "2.15.0"), Dist("aebench", "0.2"),
         Dist(None, "1"))
    assert freeze.packages_sha256() == first  # order, the project and a nameless dist aside
    fake(Dist("torch", "2.15.1"), Dist("z3-solver", "4.15"))
    assert freeze.packages_sha256() != first
