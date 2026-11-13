"""The freeze of the paper's engine and governance sets, and the paper unlock (spec C10, L8).

The answers of the paper's four industries open only through an ``EvaluationUnlock``, and
``unlock_paper`` is the only function that issues one. It does so only when:

- the engine is clean, its fingerprint is the one ``freeze_engine`` recorded, the vendored
  clones and installed packages are the recorded ones (``check_environment``), and the
  recorded commit is an ancestor of HEAD whose engine tree equals HEAD's;
- every governance set given verifies against its manifest, has been frozen by
  ``freeze_set``, and still matches the separate record ``freeze_set`` wrote for it under
  ``FREEZE_DIR/sets/``;
- each set was drafted on that frozen engine (its manifest's ``engine_fingerprint``) and
  after the freeze: its ``started_at`` (taken before the first model call) and its
  ``drafted_at`` are both strictly later than the engine's ``frozen_at``;
- there is at least one ``blind`` and one ``informed`` set, with distinct names;
- every set's manifest records ``inputs_sha256``, the sha256 of
  ``data/evaluation/inputs.json`` when it was drafted, all the same, and equal to the
  file's sha256 now (final review I6: the reviewed inputs are part of the freeze);
- (final review I7, so that the order rests on git, not on writable timestamps) the
  engine record, each set record ``FREEZE_DIR/sets/<name>.json``, each set's
  ``manifest.json`` and ``templates/*.json`` and the inputs file lie inside ``root``, are
  tracked by git, and are unchanged against HEAD (on disk and in the index); and every
  commit that touched the engine record is a strict ancestor of every commit that added
  a set record (the engine record was committed before any set was frozen). The engine
  record given must therefore be the one inside the repository (``FREEZE_DIR``).

The engine is every file git tracks under ``ENGINE_DIRS`` (``tonomyx/``, ``aebench/`` and
the tracked baseline folders ``baselines/nemo_config/`` and ``baselines/llama_guard_format/``)
except ``EXCLUDED_DIRS`` (``aebench/report/`` and ``aebench/analysis/``: post-hoc analysis
may change after results; the arms, guards, baseline configuration, inputs and runner may
not). Its fingerprint is
the sha256 of the sorted lines ``<path> NUL <sha256 of the working-tree content> LF`` of
``git ls-files`` over that pathspec. It hashes the content on disk, not git's index, so a
change hidden from ``git status`` still changes it. ``EngineDirty`` is raised, over the same
pathspec, when:

- ``root`` is not the top of its git work tree (a repo-local ``core.worktree`` would point
  the checks at other files);
- ``git status`` shows anything (untracked files included, whatever the repo's config says);
- an ignored file is anything but a bytecode cache (``__pycache__/*.pyc``), since ignored
  files are not part of the fingerprint;
- a file carries git's assume-unchanged or skip-worktree flag, or is unmerged;
- a tracked entry is a symlink or a submodule, or a symlink lies on the way to a tracked
  file (a symlink's behaviour is not in its target string).

The engine record also names what the baselines run on (final ruling I3): ``baselines``, the
``head`` commit and a ``clean`` flag of each vendored clone of ``BASELINE_CLONES`` (read with
``git -C baselines/<name>``, no network; a folder that is not the top of its own git work tree
has no head), and ``packages_sha256``, the sha256 of the sorted ``name==version`` lines of the
installed distributions (``importlib.metadata``) other than the project's own
(``PROJECT_DISTRIBUTION``). ``freeze_engine`` refuses while a clone is missing or not clean;
``unlock_paper`` (and, per episode, ``paper_freeze_ok``) refuses when the current heads, clean
flags or packages hash differ from the record (``check_environment``), or the record has none.

A set's hash is the sha256 of the sorted lines ``templates/<file> NUL <sha256> LF`` of its
``templates/*.json``. ``freeze_set`` adds ``set_hash``, ``frozen_at`` and
``frozen_manifest_sha256`` (the sha256 of the canonical JSON of the rest of the manifest)
to ``manifest.json``, so an edit of the manifest after the freeze (its dates, its
``engine_fingerprint``, its mode) is detected as well as an edit of a template; a
``templates/`` folder, ``manifest.json`` or template that is a symlink is refused.

``EvaluationUnlock`` is a capability, not a proof against someone editing this module: in
Python any object can be built around its constructor. So it is closed on every ordinary
road. Its constructor demands a module-private sentinel, it cannot be subclassed, it is
immutable, it refuses pickling (a pickle could be crafted, or carried into a process whose
engine was never checked) and a copy returns the same object. And ``is_issued``, which
``answer_side`` asks, accepts only an instance that ``unlock_paper`` itself registered, so
an instance built with ``object.__new__``, or even with the sentinel, opens nothing. An
unlock lives in one process: each evaluation process unlocks for itself.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import itertools
import json
import os
import re
import subprocess
import tempfile
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, NoReturn, final

from tonomyx.config import REPO_ROOT

FREEZE_DIR: Final[Path] = REPO_ROOT / "data/evaluation/freeze"
# The reviewed case inputs, relative to the repository (tonomyx.bench.inputs.INPUTS_PATH).
INPUTS_REL: Final[str] = "data/evaluation/inputs.json"
# The engine is every tracked file of these folders but the excluded ones: post-hoc analysis
# and reporting may change after results; the arms, guards, inputs and runner may not.
ENGINE_DIRS: Final[tuple[str, ...]] = (
    "tonomyx", "aebench", "baselines/nemo_config", "baselines/llama_guard_format",
)
EXCLUDED_DIRS: Final[tuple[str, ...]] = ("aebench/report", "aebench/analysis")
# The vendored clones of the baselines (gitignored; each is its own git repository).
BASELINE_CLONES: Final[tuple[str, ...]] = (
    "agentdojo", "camel", "nemo_guardrails", "purple_llama", "progent",
)
# The project's own distribution, left out of the packages hash (the engine covers it).
PROJECT_DISTRIBUTION: Final[str] = "aebench"
MODES: Final[tuple[str, ...]] = ("blind", "informed")
# The keys freeze_set adds to a manifest; the digest covers every key but its own.
_DIGEST_KEY: Final[str] = "frozen_manifest_sha256"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_SET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class FreezeError(Exception):
    """A freeze cannot be made or read."""


class EngineDirty(FreezeError):
    """The engine's tree is not clean, so it has no fingerprint."""


class SetChanged(FreezeError):
    """A governance set no longer matches its manifest or its freeze."""


class UnlockRefused(FreezeError):
    """The paper's answers stay closed."""


@dataclass(frozen=True)
class EngineFreeze:
    fingerprint: str
    commit: str
    frozen_at: str
    # Each vendored clone's {"head", "clean"}, and the installed packages' hash (I3); None in
    # a record that has none (the unlock then refuses).
    baselines: Mapping[str, Mapping[str, Any]] | None = None
    packages_sha256: str | None = None


@dataclass(frozen=True)
class SetFreeze:
    name: str
    mode: str
    set_hash: str
    engine_fingerprint: str
    drafted_at: str
    frozen_at: str | None  # None: verified but not frozen
    started_at: str | None = None  # when drafting began (None in a manifest without it)
    inputs_sha256: str | None = None  # the inputs file's sha256 at drafting (I6)


def _now() -> str:
    # Microseconds (Task 10 N1): a fast legitimate flow is never refused for one second.
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs_sha256(path: Path) -> str:
    """The sha256 of the inputs file (final review I6). Raises ``FreezeError``."""
    try:
        return _sha(Path(path))
    except OSError:
        raise FreezeError(f"no readable inputs file at {path}") from None


def _time(value: object, what: str) -> datetime:
    if not isinstance(value, str):
        raise FreezeError(f"{what} is not a timestamp")
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        raise FreezeError(f"{what} is not an ISO timestamp") from None
    if when.tzinfo is None:
        raise FreezeError(f"{what} has no time zone")
    return when


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    """Write through a temporary file and a rename, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _digest(lines: Sequence[tuple[bytes, str]]) -> str:
    h = hashlib.sha256()
    for path, sha in sorted(lines):
        h.update(path + b"\0" + sha.encode("ascii") + b"\n")
    return h.hexdigest()


# --- the engine ----------------------------------------------------------------------------


def engine_pathspec() -> list[str]:
    """The git pathspec of the engine: ``ENGINE_DIRS`` without ``EXCLUDED_DIRS``."""
    return ["--", *ENGINE_DIRS, *(f":(exclude){d}" for d in EXCLUDED_DIRS)]


def _git_run(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    # The repo is the one at root, whatever the caller's GIT_DIR or GIT_INDEX_FILE say.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), "-c", "core.fsmonitor=false",
             "-c", "core.ignorecase=false", *args],
            check=False, capture_output=True, env=env,
        )
    except OSError as e:
        raise FreezeError(f"git {args[0]} could not run in {root}") from e


def _git(root: Path, *args: str) -> bytes:
    done = _git_run(root, *args)
    if done.returncode != 0:
        raise FreezeError(f"git {args[0]} failed in {root}")
    return done.stdout


def _git_yes(root: Path, *args: str) -> bool:
    """A git question answered by its exit code: 0 yes, 1 no, anything else an error."""
    done = _git_run(root, *args)
    if done.returncode not in (0, 1):
        raise FreezeError(f"git {args[0]} failed in {root}")
    return done.returncode == 0


def _require_top(root: Path) -> None:
    """``root`` must be the top of its own work tree: a repo-local ``core.worktree`` (or a
    subfolder given as root) would point every check at other files."""
    top = os.fsdecode(_git(root, "rev-parse", "--show-toplevel").rstrip(b"\n"))
    if Path(top).resolve() != root.resolve():
        raise EngineDirty(f"{root} is not the top of its git work tree")


def _no_symlink_on_the_way(root: Path, rel: str, seen: set[Path]) -> None:
    """Refuse a symlink at ``rel`` or at any folder between it and ``root``."""
    path = root / rel
    while path != root and path not in seen:
        if path.is_symlink():
            raise EngineDirty(f"the engine has a symlink ({path.relative_to(root)})")
        seen.add(path)
        path = path.parent


def engine_fingerprint(root: Path = REPO_ROOT) -> str:
    """The fingerprint of the engine's tracked files at ``root``. Raises ``EngineDirty``."""
    root = Path(root)
    _require_top(root)
    spec = engine_pathspec()
    status = _git(
        root, "status", "--porcelain=v1", "-z", "--untracked-files=normal",
        "--ignore-submodules=none", *spec,
    )
    if status:
        n = status.count(b"\0")
        raise EngineDirty(f"the engine has uncommitted changes ({n} paths)")
    # Ignored files are outside the fingerprint, so only bytecode caches may be ignored.
    ignored = _git(root, "ls-files", "-o", "-i", "--exclude-standard", "-z", *spec)
    for rel in (e for e in ignored.split(b"\0") if e):
        if not (b"/__pycache__/" in b"/" + rel and rel.endswith((b".pyc", b".pyo"))):
            raise EngineDirty("the engine has an ignored file that is not a bytecode cache")
    listed = [e for e in _git(root, "ls-files", "-v", "-s", "-z", *spec).split(b"\0") if e]
    if not listed:
        raise EngineDirty(f"no tracked file under {', '.join(ENGINE_DIRS)}")
    seen: set[Path] = set()
    for folder in ENGINE_DIRS:
        _no_symlink_on_the_way(root, folder, seen)
    lines: list[tuple[bytes, str]] = []
    for entry in listed:
        # "<tag> <mode> <object> <stage>\t<path>"
        head, _, rel = entry.partition(b"\t")
        tag, mode = head[:2], head[2:].split(b" ")[0]
        if tag != b"H ":  # assume-unchanged (lower case), skip-worktree (S), unmerged (M)...
            raise EngineDirty(f"the engine has a file git does not watch ({tag!r})")
        if mode not in (b"100644", b"100755"):  # 120000 symlink, 160000 submodule
            raise EngineDirty(f"the engine has a tracked entry of mode {mode.decode()}")
        name = os.fsdecode(rel)
        _no_symlink_on_the_way(root, name, seen)
        try:
            data = (root / name).read_bytes()
        except OSError:
            raise EngineDirty("the engine has a tracked path that is not a file") from None
        lines.append((rel, hashlib.sha256(data).hexdigest()))
    return _digest(lines)


def baseline_heads(root: Path = REPO_ROOT) -> dict[str, dict[str, Any]]:
    """Each vendored clone's ``{"head": <commit or None>, "clean": bool}``. A clone is clean
    when ``git status`` shows nothing (untracked files included); a folder that is missing or
    is not the top of its own work tree has no head and is not clean."""
    heads: dict[str, dict[str, Any]] = {}
    for name in BASELINE_CLONES:
        clone = Path(root) / "baselines" / name
        head: str | None = None
        clean = False
        if clone.is_dir() and not clone.is_symlink():
            top = _git_run(clone, "rev-parse", "--show-toplevel")
            if top.returncode == 0 and (
                Path(os.fsdecode(top.stdout.rstrip(b"\n"))).resolve() == clone.resolve()
            ):
                rev = _git_run(clone, "rev-parse", "HEAD")
                status = _git_run(clone, "status", "--porcelain=v1", "-z",
                                  "--untracked-files=normal", "--ignore-submodules=none")
                if rev.returncode == 0:
                    head = rev.stdout.decode("ascii").strip()
                    clean = status.returncode == 0 and not status.stdout
        heads[name] = {"head": head, "clean": clean}
    return heads


def packages_sha256() -> str:
    """The sha256 of the sorted ``name==version`` lines (names normalized as pip does) of the
    installed distributions, without ``PROJECT_DISTRIBUTION``. No subprocess."""
    lines: set[str] = set()
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name") if dist.metadata is not None else None
        if not name:
            continue
        normalized = re.sub(r"[-_.]+", "-", str(name)).lower()
        if normalized != PROJECT_DISTRIBUTION:
            lines.add(f"{normalized}=={dist.version}")
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def check_environment(engine: EngineFreeze, root: Path = REPO_ROOT) -> None:
    """The vendored clones' heads and clean flags and the installed packages' hash are the
    ones the engine record names. Raises ``FreezeError``."""
    if engine.baselines is None or engine.packages_sha256 is None:
        raise FreezeError("the engine freeze records no baseline clones or packages")
    current = baseline_heads(root)
    recorded = {n: (v.get("head"), v.get("clean")) for n, v in engine.baselines.items()}
    now = {n: (v.get("head"), v.get("clean")) for n, v in current.items()}
    differ = sorted(n for n in set(recorded) | set(now) if recorded.get(n) != now.get(n))
    if differ:
        raise FreezeError(f"baseline clones differ from the engine freeze: {', '.join(differ)}")
    if packages_sha256() != engine.packages_sha256:
        raise FreezeError("the installed packages differ from the engine freeze")


def _read_baselines(raw: object, path: Path) -> dict[str, dict[str, Any]] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or not all(
        isinstance(v, dict) and set(v) == {"head", "clean"} and isinstance(v["clean"], bool)
        and (v["head"] is None or (isinstance(v["head"], str) and _COMMIT.fullmatch(v["head"])))
        for v in raw.values()
    ):
        raise FreezeError(f"the engine freeze at {path} has unreadable baselines")
    return {str(n): dict(v) for n, v in raw.items()}


def read_engine_freeze(path: Path | None = None) -> EngineFreeze:
    path = Path(path) if path is not None else FREEZE_DIR / "engine.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise FreezeError(f"no readable engine freeze at {path}") from None
    if not isinstance(data, dict):
        raise FreezeError(f"the engine freeze at {path} is not an object")
    fingerprint, commit, frozen_at = (data.get(k) for k in ("fingerprint", "commit", "frozen_at"))
    if not (isinstance(fingerprint, str) and _HEX64.fullmatch(fingerprint)):
        raise FreezeError(f"the engine freeze at {path} has no fingerprint")
    if not (isinstance(commit, str) and _COMMIT.fullmatch(commit)):
        raise FreezeError(f"the engine freeze at {path} has no commit")
    _time(frozen_at, f"the engine freeze at {path}: frozen_at")
    baselines = _read_baselines(data.get("baselines"), path)
    packages = data.get("packages_sha256")
    if packages is not None and not (isinstance(packages, str) and _HEX64.fullmatch(packages)):
        raise FreezeError(f"the engine freeze at {path} has an unreadable packages_sha256")
    return EngineFreeze(fingerprint, commit, str(frozen_at), baselines, packages)


def check_engine_commit(engine: EngineFreeze, root: Path = REPO_ROOT) -> None:
    """The recorded commit is an ancestor of HEAD and its engine tree is HEAD's. Raises
    ``FreezeError``."""
    root = Path(root)
    if _git_run(root, "cat-file", "-e", f"{engine.commit}^{{commit}}").returncode != 0:
        raise FreezeError("the engine freeze names a commit this repo does not have")
    if not _git_yes(root, "merge-base", "--is-ancestor", engine.commit, "HEAD"):
        raise FreezeError("the engine freeze's commit is not an ancestor of HEAD")
    same = _git_yes(
        root, "diff", "--quiet", "--no-ext-diff", "--no-textconv", "--no-renames",
        engine.commit, "HEAD", *engine_pathspec(),
    )
    if not same:
        raise FreezeError("the engine at HEAD differs from the engine at the frozen commit")


def _keep_copy(path: Path, stamp: str) -> Path:
    """Copy ``path`` next to itself under a timestamped name, never over an existing file."""
    safe = re.sub(r"[^0-9A-Za-z]", "", stamp) or "record"
    for n in itertools.count():
        copy = path.with_name(f"{path.stem}.{safe}{'' if n == 0 else f'.{n}'}{path.suffix}")
        try:
            with copy.open("xb") as f:
                f.write(path.read_bytes())
        except FileExistsError:
            continue
        return copy
    raise AssertionError("unreachable")


def freeze_engine(
    out: Path | None = None, root: Path = REPO_ROOT, *, replace: bool = False
) -> EngineFreeze:
    """Record the clean engine's fingerprint, commit and time, the vendored clones' heads and
    the installed packages' hash in ``out`` (default ``FREEZE_DIR / "engine.json"``). Raises
    ``EngineDirty`` while a clone is missing or not clean.

    Freezing the same engine (same fingerprint, clones and packages) again returns the
    existing record unchanged (its ``frozen_at`` must not move past sets drafted since). A
    record of another engine is replaced only with ``replace``, and the old record is kept as
    a timestamped copy next to it.
    """
    out = Path(out) if out is not None else FREEZE_DIR / "engine.json"
    fingerprint = engine_fingerprint(root)
    heads = baseline_heads(Path(root))
    unclean = sorted(n for n, v in heads.items() if not (v["head"] and v["clean"]))
    if unclean:
        raise EngineDirty(f"baseline clones missing or not clean: {', '.join(unclean)}")
    packages = packages_sha256()
    if out.exists():
        existing = read_engine_freeze(out)
        if (existing.fingerprint, existing.baselines, existing.packages_sha256) == (
            fingerprint, heads, packages
        ):
            return existing
        if not replace:
            raise FreezeError(f"{out} records another engine; replace it explicitly")
        _keep_copy(out, existing.frozen_at)
    commit = _git(Path(root), "rev-parse", "HEAD").decode("ascii").strip()
    frozen = EngineFreeze(fingerprint, commit, _now(), heads, packages)
    _write_json(out, {"fingerprint": frozen.fingerprint, "commit": commit,
                      "frozen_at": frozen.frozen_at, "baselines": heads,
                      "packages_sha256": packages})
    return frozen


# --- governance sets -----------------------------------------------------------------------


def set_hash(set_dir: Path) -> str:
    """The hash of a set's ``templates/*.json``."""
    templates = Path(set_dir) / "templates"
    return _digest([
        (f"templates/{p.name}".encode(), _sha(p)) for p in sorted(templates.glob("*.json"))
    ])


def _manifest_digest(manifest: Mapping[str, Any]) -> str:
    rest = {k: v for k, v in manifest.items() if k != _DIGEST_KEY}
    text = json.dumps(rest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _changed(set_dir: Path, why: str) -> NoReturn:
    raise SetChanged(f"{set_dir}: {why}")


def _read_manifest(set_dir: Path) -> dict[str, Any]:
    if (set_dir / "manifest.json").is_symlink():
        _changed(set_dir, "manifest.json is a symlink")
    try:
        manifest = json.loads((set_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _changed(set_dir, "no readable manifest.json")
    if not isinstance(manifest, dict):
        _changed(set_dir, "manifest.json is not an object")
    return manifest


def verify_set(set_dir: Path) -> SetFreeze:
    """Check the set's templates against its manifest, and against its freeze when it has
    one. Raises ``SetChanged``; ``frozen_at`` is None for a set not yet frozen."""
    set_dir = Path(set_dir)
    manifest = _read_manifest(set_dir)
    name, mode = manifest.get("name"), manifest.get("mode")
    fingerprint, drafted_at = manifest.get("engine_fingerprint"), manifest.get("drafted_at")
    processes, started_at = manifest.get("processes"), manifest.get("started_at")
    inputs = manifest.get("inputs_sha256")
    if "invalid" in manifest:
        _changed(set_dir, "the manifest is marked invalid")
    if not (isinstance(name, str) and name):
        _changed(set_dir, "the manifest has no name")
    if mode not in MODES:
        _changed(set_dir, f"the manifest's mode is not one of {MODES}")
    if not isinstance(fingerprint, str) or not isinstance(drafted_at, str):
        _changed(set_dir, "the manifest has no engine_fingerprint or drafted_at")
    if started_at is not None and not isinstance(started_at, str):
        _changed(set_dir, "the manifest's started_at is not a string")
    if inputs is not None and not (isinstance(inputs, str) and _HEX64.fullmatch(inputs)):
        _changed(set_dir, "the manifest's inputs_sha256 is not a sha256")
    if not isinstance(processes, dict):
        _changed(set_dir, "the manifest has no processes")
    expected: dict[str, str] = {}
    for pid, entry in processes.items():
        sha = entry.get("sha256") if isinstance(entry, dict) else None
        if sha is not None:
            if not isinstance(sha, str):
                _changed(set_dir, "a process hash is not a string")
            expected[f"{pid}.json"] = sha
    templates = set_dir / "templates"
    if templates.is_symlink():
        _changed(set_dir, "templates/ is a symlink")
    present = sorted(templates.iterdir()) if templates.is_dir() else []
    for p in present:
        if p.is_symlink() or not p.is_file() or p.name not in expected:
            _changed(set_dir, "templates/ holds a file the manifest does not list")
    if {p.name for p in present} != set(expected):
        _changed(set_dir, "a template the manifest lists is missing")
    for p in present:
        if _sha(p) != expected[p.name]:
            _changed(set_dir, "a template no longer matches its hash")
    current = set_hash(set_dir)
    frozen_at = manifest.get("frozen_at")
    if frozen_at is not None or "set_hash" in manifest or _DIGEST_KEY in manifest:
        if manifest.get(_DIGEST_KEY) != _manifest_digest(manifest):
            _changed(set_dir, "the manifest changed after the freeze")
        if manifest.get("set_hash") != current or not isinstance(frozen_at, str):
            _changed(set_dir, "the templates changed after the freeze")
    return SetFreeze(name, str(mode), current, fingerprint, drafted_at, frozen_at, started_at,
                     inputs)


def _record_path(freeze_dir: Path, name: str) -> Path:
    if not _SET_NAME.fullmatch(name):
        raise FreezeError(f"set name {name!r} cannot name a freeze record")
    return freeze_dir / "sets" / f"{name}.json"


def read_set_record(name: str, freeze_dir: Path | None = None) -> dict[str, str]:
    """The record ``freeze_set`` wrote for set ``name``: its ``set_hash``, ``mode`` and
    ``frozen_at``. Raises ``FreezeError``."""
    path = _record_path(Path(freeze_dir) if freeze_dir is not None else FREEZE_DIR, name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise FreezeError(f"no readable freeze record for set {name!r} at {path}") from None
    keys = ("set_hash", "mode", "frozen_at")
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) for k in keys):
        raise FreezeError(f"the freeze record of set {name!r} is incomplete")
    return {k: str(data[k]) for k in keys}


def _check_record(s: SetFreeze, freeze_dir: Path | None) -> None:
    record = read_set_record(s.name, freeze_dir)
    if (record["set_hash"], record["mode"], record["frozen_at"]) != (
        s.set_hash, s.mode, s.frozen_at
    ):
        raise SetChanged(f"set {s.name!r} no longer matches its freeze record")


def freeze_set(set_dir: Path, *, freeze_dir: Path | None = None) -> SetFreeze:
    """Verify the set, record its ``set_hash``, ``mode`` and ``frozen_at`` in
    ``<freeze_dir>/sets/<name>.json`` (default ``FREEZE_DIR``; never overwritten), and write
    ``set_hash``, ``frozen_at`` and the manifest's own digest into ``manifest.json``. A set
    already frozen is checked against its record and returned unchanged."""
    set_dir = Path(set_dir)
    records = Path(freeze_dir) if freeze_dir is not None else FREEZE_DIR
    verified = verify_set(set_dir)
    if verified.frozen_at is not None:
        _check_record(verified, records)
        return verified
    if not any((set_dir / "templates").glob("*.json")):
        raise FreezeError(f"{set_dir}: no template to freeze")
    _time(verified.drafted_at, f"{set_dir}: drafted_at")
    if verified.started_at is not None:
        _time(verified.started_at, f"{set_dir}: started_at")
    record = _record_path(records, verified.name)
    frozen_at = _now()
    record.parent.mkdir(parents=True, exist_ok=True)
    try:
        with record.open("x", encoding="utf-8") as f:  # claims the name; never overwrites
            f.write(json.dumps({"set_hash": verified.set_hash, "mode": verified.mode,
                                "frozen_at": frozen_at}, indent=2) + "\n")
    except FileExistsError:
        raise FreezeError(f"a set named {verified.name!r} is already frozen ({record})") from None
    manifest = _read_manifest(set_dir)
    manifest["set_hash"] = verified.set_hash
    manifest["frozen_at"] = frozen_at
    manifest[_DIGEST_KEY] = _manifest_digest(manifest)
    _write_json(set_dir / "manifest.json", manifest)
    frozen = verify_set(set_dir)
    if frozen.set_hash != verified.set_hash:
        _changed(set_dir, "the templates changed while freezing")
    return frozen


# --- the unlock ----------------------------------------------------------------------------

_SENTINEL: Final = object()
_ISSUED: weakref.WeakSet[EvaluationUnlock] = weakref.WeakSet()


@final
class EvaluationUnlock:
    """The capability to read the answers of a paper case. Only ``unlock_paper`` issues
    one; see the module docstring for why it cannot be built, changed, copied or pickled
    into a working one."""

    __slots__ = ("_engine", "_sets", "_unlocked_at", "_inputs_sha256", "__weakref__")
    _engine: EngineFreeze
    _sets: tuple[SetFreeze, ...]
    _unlocked_at: str
    _inputs_sha256: str | None

    def __init__(
        self, token: object, engine: EngineFreeze, sets: tuple[SetFreeze, ...],
        unlocked_at: str, inputs_sha256: str | None = None,
    ) -> None:
        if token is not _SENTINEL:
            raise TypeError("an EvaluationUnlock is issued only by unlock_paper")
        object.__setattr__(self, "_engine", engine)
        object.__setattr__(self, "_sets", tuple(sets))
        object.__setattr__(self, "_unlocked_at", unlocked_at)
        object.__setattr__(self, "_inputs_sha256", inputs_sha256)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("EvaluationUnlock cannot be subclassed")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("an EvaluationUnlock is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("an EvaluationUnlock is immutable")

    def __reduce_ex__(self, protocol: Any) -> NoReturn:
        raise TypeError("an EvaluationUnlock cannot be pickled; unlock in each process")

    def __reduce__(self) -> NoReturn:
        raise TypeError("an EvaluationUnlock cannot be pickled; unlock in each process")

    def __copy__(self) -> EvaluationUnlock:
        return self

    def __deepcopy__(self, memo: Any) -> EvaluationUnlock:
        return self

    @property
    def engine(self) -> EngineFreeze:
        return self._engine

    @property
    def sets(self) -> tuple[SetFreeze, ...]:
        return self._sets

    @property
    def unlocked_at(self) -> str:
        return self._unlocked_at

    @property
    def inputs_sha256(self) -> str | None:
        """The sha256 of the inputs file the sets were drafted with (I6)."""
        return self._inputs_sha256

    @property
    def set_hashes(self) -> dict[str, str]:
        """The verified hash of each set, by name, to record with each run."""
        return {s.name: s.set_hash for s in self._sets}

    def __repr__(self) -> str:
        return (
            f"EvaluationUnlock(engine={self._engine.fingerprint[:12]},"
            f" sets={sorted(self.set_hashes)}, unlocked_at={self._unlocked_at})"
        )


def is_issued(unlock: object) -> bool:
    """Whether ``unlock`` is an unlock that ``unlock_paper`` issued in this process."""
    return isinstance(unlock, EvaluationUnlock) and unlock in _ISSUED


def _inside(root: Path, path: Path, what: str) -> str:
    """``path`` relative to ``root`` (as git names it), refusing a path outside it."""
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        raise UnlockRefused(f"{what} lies outside the repository at {root}") from None


def _require_committed(root: Path, rels: Sequence[str]) -> None:
    """Every path is a regular file tracked in HEAD, with the same content on disk and in
    the index as in HEAD (final review I7). Raises ``UnlockRefused``."""
    seen: set[Path] = set()
    try:
        for rel in rels:
            _no_symlink_on_the_way(root, rel, seen)
        listed = _git(root, "ls-tree", "-z", "--full-tree", "HEAD", "--", *rels)
        heads: dict[str, tuple[bytes, str]] = {}
        for entry in (e for e in listed.split(b"\0") if e):
            head, _, name = entry.partition(b"\t")
            mode, kind, blob = head.split(b" ")
            if kind == b"blob":
                heads[os.fsdecode(name)] = (mode, blob.decode("ascii"))
        missing = [r for r in rels if r not in heads or heads[r][0] not in (b"100644", b"100755")]
        if missing:
            raise UnlockRefused(
                f"freeze files not committed to git={len(missing)} (first: {missing[0]})"
            )
        disk = _git(root, "hash-object", "--no-filters", "--", *rels).decode("ascii").split()
        changed = [r for r, blob in zip(rels, disk, strict=True) if heads[r][1] != blob]
        if changed:
            raise UnlockRefused(
                f"freeze files changed since HEAD={len(changed)} (first: {changed[0]})"
            )
        if not _git_yes(root, "diff", "--cached", "--quiet", "--no-ext-diff", "HEAD", "--",
                        *rels):
            raise UnlockRefused("freeze files have staged changes")
    except UnlockRefused:
        raise
    except FreezeError as e:
        raise UnlockRefused(f"freeze files: {e}") from e


def _commits(root: Path, rel: str, *, added: bool = False) -> list[str]:
    args = ["log", "--full-history", "--format=%H"]
    if added:
        args.append("--diff-filter=A")
    return _git(root, *args, "--", rel).decode("ascii").split()


def _require_order(root: Path, engine_rel: str, record_rels: Sequence[str]) -> None:
    """Every commit that touched the engine record is a strict ancestor of every commit that
    added a set record. Raises ``UnlockRefused``."""
    try:
        engine_commits = _commits(root, engine_rel)
        for rel in record_rels:
            added = _commits(root, rel, added=True)
            if not added:
                raise UnlockRefused(f"{rel}: no commit added the set record")
            for set_commit in added:
                for engine_commit in engine_commits:
                    if engine_commit == set_commit or not _git_yes(
                        root, "merge-base", "--is-ancestor", engine_commit, set_commit
                    ):
                        raise UnlockRefused(
                            f"{rel}: the set record was committed before or with the engine"
                            " record"
                        )
    except UnlockRefused:
        raise
    except FreezeError as e:
        raise UnlockRefused(f"freeze order: {e}") from e


def unlock_paper(
    engine_freeze: Path, set_dirs: Sequence[Path], root: Path = REPO_ROOT,
    inputs_path: Path | None = None,
) -> EvaluationUnlock:
    """Issue the unlock when every check of the module docstring passes, else raise
    ``UnlockRefused``. ``inputs_path`` defaults to ``root / INPUTS_REL``."""
    root = Path(root)
    try:
        engine = read_engine_freeze(engine_freeze)
        engine_at = _time(engine.frozen_at, "the engine's frozen_at")
    except FreezeError as e:
        raise UnlockRefused(f"engine freeze: {e}") from e
    try:
        current = engine_fingerprint(root)
    except FreezeError as e:
        raise UnlockRefused(f"the engine is not clean: {e}") from e
    if current != engine.fingerprint:
        raise UnlockRefused("the engine's fingerprint is not the frozen one")
    try:
        check_environment(engine, root)
    except FreezeError as e:
        raise UnlockRefused(f"baselines: {e}") from e
    try:
        check_engine_commit(engine, root)
    except FreezeError as e:
        raise UnlockRefused(f"engine commit: {e}") from e
    records = Path(engine_freeze).parent
    sets: list[SetFreeze] = []
    for set_dir in set_dirs:
        try:
            s = verify_set(Path(set_dir))
        except SetChanged as e:
            raise UnlockRefused(f"a set changed: {e}") from e
        if s.frozen_at is None:
            raise UnlockRefused(f"{set_dir}: the set is not frozen")
        try:
            _check_record(s, records)
        except SetChanged as e:
            raise UnlockRefused(f"a set changed: {e}") from e
        except FreezeError as e:
            raise UnlockRefused(f"{set_dir}: {e}") from e
        if s.engine_fingerprint != engine.fingerprint:
            raise UnlockRefused(f"{set_dir}: the set was drafted on another engine")
        if s.started_at is None:
            raise UnlockRefused(f"{set_dir}: the set does not record when drafting started")
        try:
            started = _time(s.started_at, f"{set_dir}: started_at")
            drafted = _time(s.drafted_at, f"{set_dir}: drafted_at")
        except FreezeError as e:
            raise UnlockRefused(str(e)) from e
        if not (started > engine_at and drafted > engine_at):
            raise UnlockRefused(f"{set_dir}: the set was drafted before the engine freeze")
        sets.append(s)
    names = [s.name for s in sets]
    if len(set(names)) != len(names):
        raise UnlockRefused("two sets share a name")
    if not all(any(s.mode == mode for s in sets) for mode in MODES):
        raise UnlockRefused("the unlock needs at least one blind and one informed set")
    # I6: the reviewed inputs the sets were drafted with are the inputs now.
    inputs_file = Path(inputs_path) if inputs_path is not None else root / INPUTS_REL
    recorded = {s.inputs_sha256 for s in sets}
    if None in recorded:
        raise UnlockRefused("a set does not record the inputs it was drafted with")
    if len(recorded) != 1:
        raise UnlockRefused("the sets were drafted with different inputs files")
    try:
        current_inputs = inputs_sha256(inputs_file)
    except FreezeError as e:
        raise UnlockRefused(str(e)) from e
    if recorded != {current_inputs}:
        raise UnlockRefused("the inputs file changed since the sets were drafted")
    # I7: the freeze files are committed, unchanged, and in order in git.
    engine_rel = _inside(root, Path(engine_freeze), "the engine freeze")
    record_rels = [_inside(root, _record_path(records, s.name), f"the record of {s.name}")
                   for s in sets]
    files = [engine_rel, *record_rels, _inside(root, inputs_file, "the inputs file")]
    for set_dir in set_dirs:
        files.append(_inside(root, Path(set_dir) / "manifest.json", f"{set_dir}"))
        files += [_inside(root, t, f"{set_dir}")
                  for t in sorted((Path(set_dir) / "templates").glob("*.json"))]
    _require_committed(root, list(dict.fromkeys(files)))
    _require_order(root, engine_rel, record_rels)
    unlock = EvaluationUnlock(_SENTINEL, engine, tuple(sets), _now(), current_inputs)
    _ISSUED.add(unlock)
    return unlock
