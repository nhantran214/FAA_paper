"""aebench: the evaluation on bench_v1."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from tonomyx.bench.cases import BENCH_ROOT, DEV_INDUSTRIES
from tonomyx.bench.freeze import (
    FREEZE_DIR,
    FreezeError,
    engine_fingerprint,
    freeze_engine,
    freeze_set,
    inputs_sha256,
)
from tonomyx.bench.inputs import (
    INPUTS_PATH,
    CaseInputs,
    load_inputs,
    placeholder_inputs,
    save_inputs,
)
from tonomyx.config import REPO_ROOT
from tonomyx.models.json_model import create_json_model

BENCHMARK_DIR = REPO_ROOT / "experiments" / "v2" / "benchmarks"
DEFAULT_DRAFT_MODEL = "gemini-3.8-flash"
# Seconds a hosted drafting call may take (rehearsal F2: informed repairs ran 4-10 minutes).
DRAFT_TIMEOUT = 900.0


def _case_dirs(only: Sequence[str] | None = None) -> dict[str, Path]:
    """Case folders by id, from the coverage list (the ids only; nothing is opened)."""
    rows = json.loads((BENCH_ROOT / "coverage.json").read_text(encoding="utf-8"))["rows"]
    ids = [r["case_id"] for r in rows]
    if only:
        ids = [i for i in ids if i in set(only)]
    return {i: BENCH_ROOT / i for i in ids}


def _counts(inputs: Mapping[str, object], dirs: dict[str, Path]) -> str:
    return f"cases={len(dirs)} with_inputs={sum(1 for i in dirs if i in inputs)}"


def _inputs_draft(args: argparse.Namespace) -> int:
    from aebench.inputs.draft import draft_inputs

    dirs = _case_dirs(args.case)
    path = Path(args.path)
    inputs = load_inputs(path)
    todo = [d for i, d in dirs.items() if args.redo or i not in inputs]
    model = create_json_model(args.model)
    made = 0

    def keep(item: CaseInputs) -> None:
        nonlocal made
        inputs[item.case_id] = item
        save_inputs(inputs, path)
        made += 1

    try:
        draft_inputs(todo, model, seed=args.seed, on_draft=keep)
    finally:
        print(f"drafted={made} total={len(inputs)}")
    return 0


def _inputs_check(args: argparse.Namespace) -> int:
    from aebench.inputs.draft import problems_of

    dirs = _case_dirs(args.case)
    inputs = load_inputs(Path(args.path))
    flagged = sum(1 for i, d in dirs.items() if i in inputs and problems_of(inputs[i], d))
    status = Counter(item.status for item in inputs.values())
    print(
        f"{_counts(inputs, dirs)} flagged={flagged} draft={status['draft']}"
        f" approved={status['approved']} rejected={status['rejected']}"
    )
    return 1 if flagged else 0


def _inputs_export(args: argparse.Namespace) -> int:
    from aebench.inputs.draft import export_sheet

    dirs = _case_dirs(args.case)
    inputs = load_inputs(Path(args.path))
    rows = export_sheet(inputs, dirs.values(), Path(args.out))
    print(f"exported={rows}")
    return 0


def _inputs_import(args: argparse.Namespace) -> int:
    from aebench.inputs.draft import import_sheet

    dirs = _case_dirs(None)
    path = Path(args.path)
    before = load_inputs(path)
    held: list[str] = []
    unknown: list[str] = []
    after = import_sheet(Path(args.sheet), before, dirs, held, unknown)
    save_inputs(after, path)
    changed = sum(1 for i in after if after[i] != before.get(i))
    status = Counter(item.status for item in after.values())
    print(
        f"changed={changed} held_as_draft={len(held)} approved={status['approved']}"
        f" unknown_case_ids={len(unknown)}"
    )
    return 0


def _draft(args: argparse.Namespace) -> int:
    from tonomyx.drafting.draft import draft_set
    from tonomyx.drafting.sources import CaseView, briefs, case_view, coverage_row

    industries = tuple(args.industries)
    default_out = REPO_ROOT / "data" / "evaluation" / "governance" / args.name
    out_dir = Path(args.out) if args.out else default_out
    # Ruling R0a: the set records the engine it was drafted on. With no fingerprint (an
    # unclean tonomyx/), only development industries may be drafted, marked "dev".
    try:
        fingerprint = engine_fingerprint()
    except FreezeError as e:
        outside = sum(1 for i in industries if i not in DEV_INDUSTRIES)
        if outside:
            print(f"refused: {e}; industries outside development={outside} need a clean engine")
            return 2
        fingerprint = "dev"
        print(f"note: {e}; the set is recorded with engine_fingerprint=dev")
    if _frozen(out_dir):
        print(f"refused: {out_dir} holds a frozen set; it is never drafted over")
        return 2
    todo = briefs(BENCH_ROOT / "axes.json", industries)
    views: dict[str, list[CaseView]] = {}
    placeholders = selected = missing = 0
    if args.mode == "informed":
        inputs = load_inputs(Path(args.inputs))
        for case_id, case_dir in _case_dirs(None).items():
            row = coverage_row(case_dir)
            if row["industry"] not in industries:
                continue
            item = inputs.get(case_id)
            if item is None or item.status != "approved":
                if row["industry"] not in DEV_INDUSTRIES:
                    missing += 1
                    continue
                item, placeholders = placeholder_inputs(case_id), placeholders + 1
            selected += 1
            if not missing:
                views.setdefault(str(row["process"]), []).append(case_view(case_dir, item))
        if missing:
            print(f"refused: cases={selected + missing} without_approved_input={missing}")
            return 2
    # I6: the set records the inputs file it was drafted with; the paper unlock compares.
    inputs_file = Path(args.inputs)
    inputs_hash = inputs_sha256(inputs_file) if inputs_file.is_file() else None
    changed = False
    try:
        results = draft_set(
            args.name, args.mode, todo, views,
            create_json_model(args.model, timeout=args.timeout), out_dir,
            seed=args.seed, engine_fingerprint=fingerprint, inputs_sha256=inputs_hash,
        )
    finally:
        # The set must have been drafted on the engine it names, start to end.
        if fingerprint != "dev" and _fingerprint_or_none() != fingerprint:
            changed = True
            _mark_invalid(out_dir, "the engine changed during drafting")
    if changed:
        print(f"refused: the engine changed during drafting; {out_dir} is marked invalid")
        return 2
    for r in results:
        print(f"{r.process_id} {r.status} rounds={r.rounds}")
    valid = sum(1 for r in results if r.status == "valid")
    print(f"processes={len(results)} valid={valid} placeholder_inputs={placeholders}")
    print(f"engine_fingerprint={fingerprint} path={out_dir}")
    return 0 if valid == len(results) else 1


def _fingerprint_or_none() -> str | None:
    try:
        return engine_fingerprint()
    except FreezeError:
        return None


def _mark_invalid(set_dir: Path, reason: str) -> None:
    """Mark a drafted set so that it can be neither frozen nor unlocked."""
    path = set_dir / "manifest.json"
    if not path.is_file():
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["invalid"] = reason
    manifest["engine_fingerprint"] = "invalid"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _frozen(set_dir: Path) -> bool:
    """Whether ``set_dir`` holds a set ``freeze_set`` froze (any of its freeze keys)."""
    try:
        manifest = json.loads((set_dir / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        return True  # unreadable: not drafted over either
    keys = {"frozen_at", "set_hash", "frozen_manifest_sha256"}
    return not isinstance(manifest, dict) or bool(keys & set(manifest))


def _freeze_engine(args: argparse.Namespace) -> int:
    try:
        frozen = freeze_engine(Path(args.out), root=REPO_ROOT, replace=args.replace)
    except FreezeError as e:
        print(f"refused: {e}")
        return 2
    print(
        f"fingerprint={frozen.fingerprint} commit={frozen.commit}"
        f" frozen_at={frozen.frozen_at} baselines={len(frozen.baselines or {})}"
        f" packages_sha256={frozen.packages_sha256} path={args.out}"
    )
    return 0


def _freeze_set(args: argparse.Namespace) -> int:
    try:
        frozen = freeze_set(Path(args.set_dir), freeze_dir=Path(args.freeze_dir))
    except FreezeError as e:
        print(f"refused: {e}")
        return 2
    from aebench.run.episode import process_statuses

    statuses = process_statuses(Path(args.set_dir))
    valid = sum(1 for _, status in statuses if status == "valid")
    print(
        f"set_hash={frozen.set_hash} mode={frozen.mode}"
        f" engine_fingerprint={frozen.engine_fingerprint} frozen_at={frozen.frozen_at}"
        f" valid={valid} total={len(statuses)} path={args.set_dir}"
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    from aebench.run.experiment import (
        DEFAULT_OUT_DIR,
        ExperimentRefused,
        load_experiment,
        run_experiment,
        status_counts,
    )
    from tonomyx.bench.freeze import UnlockRefused, unlock_paper
    from tonomyx.models.errors import ModelUnavailable

    path = Path(args.experiment)
    try:
        experiment = load_experiment(path)
        # A paper experiment unlocks in this process, after the freezes are checked.
        unlock = (
            unlock_paper(Path(args.engine_freeze), experiment.governance_sets)
            if experiment.paper
            else None
        )
        out = run_experiment(
            path, out_dir=Path(args.out) if args.out else DEFAULT_OUT_DIR, unlock=unlock,
            retry_errors=args.retry_errors,
        )
    except (ExperimentRefused, UnlockRefused) as e:
        print(f"refused: {e}")
        return 2
    except ModelUnavailable as e:
        print(f"stopped: {e}; the rows written so far are kept, run again to resume")
        return 3
    counts = status_counts(out)
    print(
        f"rows={sum(counts.values())} scored={counts['scored']} not_run={counts['not_run']}"
        f" error={counts['error']} path={out}"
    )
    return 1 if counts["error"] else 0


def _report(args: argparse.Namespace) -> int:
    from aebench.report.evaluation import ReportRefused, write_report

    path = Path(args.rows)
    with path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    out = Path(args.out)
    try:
        report = write_report(rows, out)
    except ReportRefused as e:
        print(f"refused: {e}")
        return 2
    for name in (report.name, "summary.csv", "mcnemar.csv", "defence.csv"):
        print(out / name)
    return 0


def _paper_artefacts(args: argparse.Namespace) -> int:
    from aebench.report.evaluation import ReportRefused
    from aebench.report.paper import write_paper_artefacts

    rows = []
    for name in args.rows:
        with Path(name).open(encoding="utf-8") as f:
            rows += [json.loads(line) for line in f if line.strip()]
    try:
        written = write_paper_artefacts(rows, Path(args.out))
    except ReportRefused as e:
        print(f"refused: {e}")
        return 2
    for path in written:
        print(path)
    return 0


def _cases(args: argparse.Namespace) -> int:
    from aebench.run.experiment import load_experiment, select_cases_counted
    from tonomyx.bench.cases import PAPER_INDUSTRIES

    total = missing_total = episodes = 0
    for industry in PAPER_INDUSTRIES:
        experiment = load_experiment(BENCHMARK_DIR / f"{industry}.json")
        spec = dict(experiment.cases)
        if args.statuses:
            spec["statuses"] = list(args.statuses)
        refs, missing = select_cases_counted(spec)
        print(f"{industry} cases={len(refs)} missing={missing}")
        total += len(refs)
        missing_total += missing
        episodes += (
            len(refs) * len(experiment.arms) * len(experiment.governance_sets)
            * len(experiment.models)
        )
    print(f"total cases={total} missing={missing_total}")
    print(f"episodes_per_repetition={episodes}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aebench", description="Evaluate framed autonomy on bench_v1."
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    inputs = commands.add_parser("inputs", help="neutral requests and input-fact allow-lists")
    inputs.add_argument("--path", default=str(INPUTS_PATH), help="the inputs file")
    inputs.add_argument("--case", action="append", help="limit to this case id (repeatable)")
    sub = inputs.add_subparsers(dest="inputs_command", metavar="ACTION", required=True)
    draft = sub.add_parser("draft", help="draft inputs with a model")
    draft.add_argument("--model", default=DEFAULT_DRAFT_MODEL)
    draft.add_argument("--seed", type=int, default=0)
    draft.add_argument(
        "--redo", action="store_true", help="draft again cases already in the file"
    )
    draft.set_defaults(handler=_inputs_draft)
    check = sub.add_parser("check", help="count flagged requests")
    check.set_defaults(handler=_inputs_check)
    export = sub.add_parser("export", help="write the expert CSV sheet")
    export.add_argument("--out", required=True)
    export.set_defaults(handler=_inputs_export)
    imp = sub.add_parser("import", help="apply an expert CSV sheet")
    imp.add_argument("--sheet", required=True)
    imp.set_defaults(handler=_inputs_import)
    drafting = commands.add_parser("draft", help="draft the shared governance set")
    drafting.add_argument("--mode", choices=["blind", "informed"], required=True)
    drafting.add_argument("--industries", nargs="+", required=True)
    drafting.add_argument("--name", required=True)
    drafting.add_argument("--model", default=DEFAULT_DRAFT_MODEL)
    drafting.add_argument("--seed", type=int, default=0)
    drafting.add_argument("--out", default=None, help="default data/evaluation/governance/NAME")
    drafting.add_argument("--inputs", default=str(INPUTS_PATH), help="the inputs file")
    drafting.add_argument(
        "--timeout", type=float, default=DRAFT_TIMEOUT,
        help="seconds a hosted model call may take (default %(default)s)",
    )
    drafting.set_defaults(handler=_draft)
    freezing = commands.add_parser("freeze", help="freeze the engine or a governance set")
    fsub = freezing.add_subparsers(dest="freeze_command", metavar="WHAT", required=True)
    engine = fsub.add_parser("engine", help="record the clean engine's fingerprint")
    engine.add_argument("--out", default=str(FREEZE_DIR / "engine.json"))
    engine.add_argument(
        "--replace", action="store_true",
        help="replace a freeze of another engine (the old record is kept as a copy)",
    )
    engine.set_defaults(handler=_freeze_engine)
    one_set = fsub.add_parser("set", help="verify a drafted set and freeze it")
    one_set.add_argument("set_dir")
    one_set.add_argument(
        "--freeze-dir", default=str(FREEZE_DIR),
        help="where the set's freeze record goes (next to the engine freeze)",
    )
    one_set.set_defaults(handler=_freeze_set)
    running = commands.add_parser("run", help="run an experiment (resumes where it stopped)")
    running.add_argument("experiment", help="the experiment file (JSON)")
    running.add_argument("--out", default=None, help="the results folder (default results/v2)")
    running.add_argument(
        "--engine-freeze", default=str(FREEZE_DIR / "engine.json"),
        help="the engine freeze a paper experiment unlocks against",
    )
    running.add_argument(
        "--retry-errors", action="store_true",
        help="run again the episodes whose last row has status error",
    )
    running.set_defaults(handler=_run)
    reporting = commands.add_parser("report", help="the evaluation report of a results file")
    reporting.add_argument("rows", help="the results file (JSONL)")
    reporting.add_argument("--out", required=True, help="the folder for the report files")
    reporting.set_defaults(handler=_report)
    artefacts = commands.add_parser(
        "paper-artefacts", help="the paper's tables and figures from the benchmark results"
    )
    artefacts.add_argument("rows", nargs="+", help="the results files (JSONL)")
    artefacts.add_argument("--out", required=True, help="the folder for the artefacts")
    artefacts.set_defaults(handler=_paper_artefacts)
    counting = commands.add_parser(
        "cases", help="count the cases and episodes of the four paper benchmarks"
    )
    counting.add_argument(
        "--statuses", nargs="+", metavar="S",
        help="override the files' case statuses (e.g. draft_v1 to preview)",
    )
    counting.set_defaults(handler=_cases)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    result: int = handler(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
