"""The four per-industry paper benchmarks, `aebench cases`, and the run scripts (stub AEBENCH)."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from pathlib import Path

import pytest

from aebench.cli import main
from aebench.run.experiment import load_experiment, select_cases
from tonomyx.bench.cases import PAPER_INDUSTRIES

REPO = Path(__file__).resolve().parents[2]
BENCH_DIR = REPO / "experiments" / "v2" / "benchmarks"
INDUSTRIES = ("ban_le", "phan_phoi", "van_tai", "cntt_phan_mem")
ARMS = ["full", "no-database", "prompt-only", "bare", "progent", "llama-guard",
        "nemo-guardrails", "agentdojo-defense", "camel-capability"]
PAPER_DB = "postgresql://tonomyx:tonomyx@localhost:55433/aebench_paper"
TEST_DB = "postgresql://tonomyx:tonomyx@localhost:55433/tonomyx"


def _path(ind: str) -> Path:
    return BENCH_DIR / f"{ind}.json"


def test_industries_match_the_platform() -> None:
    assert tuple(INDUSTRIES) == tuple(PAPER_INDUSTRIES)


@pytest.mark.parametrize("ind", INDUSTRIES)
def test_each_benchmark_loads_with_the_shared_protocol(ind: str) -> None:
    exp = load_experiment(_path(ind))
    assert exp.name == f"bench-{ind}"
    assert exp.paper is True
    assert list(exp.arms) == ARMS
    assert exp.guard_model == "qwen3:14b"
    assert (exp.sampling.temperature, exp.sampling.seed, exp.sampling.num_ctx) == (0.0, 1, 32768)
    assert exp.repetitions == 1
    assert list(exp.models) == ["qwen3:14b", "gpt-oss:20b", "mistral-small3.2:24b", "qwen3:30b-a3b"]
    think = {m: s.think for m, s in exp.model_sampling.items()}
    assert think == {"qwen3:14b": False, "gpt-oss:20b": "low",
                     "mistral-small3.2:24b": False, "qwen3:30b-a3b": False}
    assert exp.cases["industries"] == [ind]
    assert exp.cases["statuses"] == ["approved"]


# Every review status, so the live-data checks stay meaningful as cases move to approved.
REVIEW_STATUSES = ["draft_v1", "in_review", "approved"]


def test_benchmarks_partition_the_runnable_paper_cases() -> None:
    statuses = REVIEW_STATUSES
    selected: dict[str, set[str]] = {}
    for ind in INDUSTRIES:
        spec = dict(load_experiment(_path(ind)).cases, statuses=statuses)
        refs = select_cases(spec)
        assert {r.industry for r in refs} <= {ind}
        selected[ind] = {r.case_id for r in refs}
    ids = [i for s in selected.values() for i in s]
    assert len(ids) == len(set(ids))  # pairwise disjoint
    union = {r.case_id for r in select_cases(
        {"industries": list(PAPER_INDUSTRIES), "statuses": statuses})}
    assert set(ids) == union
    assert union  # the live data has paper cases under review or approved


def test_every_benchmark_selects_approved_cases_only() -> None:
    for ind in INDUSTRIES:
        assert load_experiment(_path(ind)).cases["statuses"] == ["approved"]


def test_benchmarks_share_one_protocol() -> None:
    def stripped(ind: str) -> dict:
        raw = json.loads(_path(ind).read_text(encoding="utf-8"))
        raw.pop("name")
        raw["cases"] = {k: v for k, v in raw["cases"].items() if k != "industries"}
        return raw
    first = stripped(INDUSTRIES[0])
    assert all(stripped(i) == first for i in INDUSTRIES[1:])


def test_paper_example_is_gone() -> None:
    assert not (REPO / "experiments" / "v2" / "paper.example.json").exists()


def _total(out: str) -> int:
    line = next(ln for ln in out.splitlines() if ln.startswith("total"))
    return int(line.split("cases=")[1].split()[0])


def test_cases_command_is_consistent(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cases", "--statuses", *REVIEW_STATUSES]) == 0
    out = capsys.readouterr().out
    counts = {}
    for ind in INDUSTRIES:
        line = next(ln for ln in out.splitlines() if ln.startswith(ind))
        counts[ind] = int(line.split("cases=")[1].split()[0])
        assert "missing=" in line
    total = _total(out)
    assert sum(counts.values()) == total
    assert total > 0
    assert "episodes_per_repetition=" in out


def test_cases_command_default_statuses(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cases"]) == 0
    out = capsys.readouterr().out
    counts = [int(ln.split("cases=")[1].split()[0]) for ln in out.splitlines()
              if ln.split()[0] in INDUSTRIES]
    total = _total(out)
    assert sum(counts) == total


# ---- scripts, with a stub AEBENCH ----

# Each call pops one token from $STUB_DIR/<subcommand>.codes: CODE[+N][eE]. CODE is the exit
# code; +N appends N rows to the run's results file first (progress); eE prints the final
# line of `aebench run` with error=E.
STUB = """#!/usr/bin/env bash
echo "$*" >> "$STUB_LOG"
sub="$1"
seq_file="$STUB_DIR/$sub.codes"
tok=0
if [ -f "$seq_file" ] && [ -s "$seq_file" ]; then
  tok=$(head -n1 "$seq_file")
  tail -n +2 "$seq_file" > "$seq_file.tmp"; mv "$seq_file.tmp" "$seq_file"
fi
code=${tok%%[!0-9]*}
grow=0; errs=""
case "$tok" in *+*) grow=${tok#*+}; grow=${grow%%[!0-9]*} ;; esac
case "$tok" in *e*) errs=${tok#*e}; errs=${errs%%[!0-9]*} ;; esac
if [ "$sub" = run ]; then
  out=""; prev=""
  for a in "$@"; do [ "$prev" = --out ] && out="$a"; prev="$a"; done
  results="$out/bench-$(basename "$2" .json).jsonl"
  for _ in $(seq 1 "$grow"); do echo '{"episode_id": "x"}' >> "$results"; done
  [ -n "$errs" ] && echo "rows=9 scored=1 not_run=0 error=$errs path=$results"
fi
exit "$code"
"""


def _setup(tmp_path: Path, run_codes: str = "") -> dict[str, str]:
    stub = tmp_path / "stub.sh"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(0o755)
    (tmp_path / "run.codes").write_text(run_codes, encoding="utf-8")
    (tmp_path / "res").mkdir()
    env = dict(os.environ)
    for name in ("RETRY_ERRORS", "AEBENCH_RUN_LOCK_HELD"):
        env.pop(name, None)
    env.update(AEBENCH=str(stub), STUB_LOG=str(tmp_path / "calls.log"), STUB_DIR=str(tmp_path),
               MAX_RETRIES="5", RETRY_SLEEP="0", TONOMYX_DATABASE_URL=PAPER_DB,
               RESULTS_DIR=str(tmp_path / "res"))
    return env


def _call(script: str, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(REPO / "scripts" / script), *args], env=env,
                          capture_output=True, text=True, timeout=60)


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _subs(tmp_path: Path) -> list[str]:
    return [c.split()[0] for c in _calls(tmp_path)]


def test_run_benchmark_retries_exit_3_then_reports(tmp_path: Path) -> None:
    env = _setup(tmp_path, "3\n0\n")
    res = _call("run_benchmark.sh", ["van_tai"], env)
    assert res.returncode == 0, res.stderr
    r = tmp_path / "res"
    exp = str(BENCH_DIR.relative_to(REPO) / "van_tai.json")
    assert _calls(tmp_path) == [
        f"run {exp} --out {r}", f"run {exp} --out {r}",
        f"report {r}/bench-van_tai.jsonl --out {r}/bench-van_tai"]
    assert (r / "bench-van_tai.log").is_file()
    assert "model server gone" in res.stderr


def test_run_benchmark_gives_up_after_max_retries_without_progress(tmp_path: Path) -> None:
    env = _setup(tmp_path, "3\n3\n3\n3\n3\n")
    env["MAX_RETRIES"] = "2"  # retries: three attempts in all
    res = _call("run_benchmark.sh", ["ban_le"], env)
    assert res.returncode == 3
    assert _subs(tmp_path) == ["run", "run", "run"]
    assert "model server gone" in res.stderr and "2 retries" in res.stderr


def test_run_benchmark_retry_budget_starts_again_after_progress(tmp_path: Path) -> None:
    # drop, progress then drop, drop, done: three retries in all, beyond MAX_RETRIES=2.
    env = _setup(tmp_path, "3\n3+1\n3\n0\n")
    env["MAX_RETRIES"] = "2"
    res = _call("run_benchmark.sh", ["ban_le"], env)
    assert res.returncode == 0, res.stderr
    assert _subs(tmp_path) == ["run", "run", "run", "run", "report"]


def test_run_benchmark_progress_on_every_drop_never_gives_up(tmp_path: Path) -> None:
    env = _setup(tmp_path, "3+1\n3+1\n3+1\n0\n")
    env["MAX_RETRIES"] = "1"
    res = _call("run_benchmark.sh", ["ban_le"], env)
    assert res.returncode == 0, res.stderr
    assert _subs(tmp_path) == ["run", "run", "run", "run", "report"]


def test_run_benchmark_default_retry_sleep_is_60s() -> None:
    text = (REPO / "scripts" / "run_benchmark.sh").read_text(encoding="utf-8")
    assert 'RETRY_SLEEP="${RETRY_SLEEP:-60}"' in text


def test_run_benchmark_exit_1_writes_the_report_and_warns(tmp_path: Path) -> None:
    env = _setup(tmp_path, "1e2\n")
    res = _call("run_benchmark.sh", ["ban_le"], env)
    assert res.returncode == 1
    assert _subs(tmp_path) == ["run", "report"]
    assert "2 error rows" in res.stderr and "RETRY_ERRORS=1" in res.stderr


def test_run_benchmark_retry_errors_passes_the_flag(tmp_path: Path) -> None:
    for sub, flag in (("on", "1"), ("off", None)):
        folder = tmp_path / sub
        folder.mkdir()
        env = _setup(folder)
        if flag is not None:
            env["RETRY_ERRORS"] = flag
        res = _call("run_benchmark.sh", ["ban_le"], env)
        assert res.returncode == 0, res.stderr
        assert _calls(folder)[0].endswith(" --retry-errors") == (flag is not None)


@pytest.mark.parametrize("code,message", [
    ("2", "refused"), ("7", "aebench exited 7 (unexpected)"),
    ("143", "aebench exited 143 (unexpected)")])
def test_run_benchmark_exit_messages(tmp_path: Path, code: str, message: str) -> None:
    env = _setup(tmp_path, f"{code}\n")
    res = _call("run_benchmark.sh", ["ban_le"], env)
    assert res.returncode == int(code)
    assert message in res.stderr
    assert _subs(tmp_path) == ["run"]


def test_run_benchmark_rejects_unknown_industry(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    res = _call("run_benchmark.sh", ["nope"], env)
    assert res.returncode != 0
    assert _calls(tmp_path) == []
    assert "ban_le" in res.stdout + res.stderr


def test_run_all_runs_four_then_artefacts(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    res = _call("run_all.sh", [], env)
    assert res.returncode == 0, res.stderr
    r = tmp_path / "res"
    calls = _calls(tmp_path)
    runs = [c for c in calls if c.startswith("run ")]
    assert [Path(c.split()[1]).stem for c in runs] == list(INDUSTRIES)
    files = " ".join(f"{r}/bench-{i}.jsonl" for i in INDUSTRIES)
    assert calls[-1] == f"paper-artefacts {files} --out {r}/paper"


def test_run_all_continues_past_error_rows_and_exits_1(tmp_path: Path) -> None:
    env = _setup(tmp_path, "0\n1e3\n0\n1e1\n")
    res = _call("run_all.sh", [], env)
    assert res.returncode == 1
    calls = _calls(tmp_path)
    assert [Path(c.split()[1]).stem for c in calls if c.startswith("run ")] == list(INDUSTRIES)
    assert sum(c.startswith("report ") for c in calls) == 4
    assert calls[-1].startswith("paper-artefacts ")
    last = res.stderr.strip().splitlines()[-1]
    assert "phan_phoi" in last and "cntt_phan_mem" in last and "ban_le" not in last


def test_run_all_stops_on_refusal(tmp_path: Path) -> None:
    env = _setup(tmp_path, "0\n2\n")
    res = _call("run_all.sh", [], env)
    assert res.returncode == 2
    runs = [c for c in _calls(tmp_path) if c.startswith("run ")]
    assert [Path(c.split()[1]).stem for c in runs] == ["ban_le", "phan_phoi"]
    assert not any(c.startswith("paper-artefacts") for c in _calls(tmp_path))
    assert "refused" in res.stderr


def test_run_all_stops_when_the_retries_give_up(tmp_path: Path) -> None:
    env = _setup(tmp_path, "3\n")
    env["MAX_RETRIES"] = "0"
    res = _call("run_all.sh", [], env)
    assert res.returncode == 3
    assert _subs(tmp_path) == ["run"]
    assert "model server gone" in res.stderr


@pytest.mark.parametrize("script,args", [("run_benchmark.sh", ["ban_le"]), ("run_all.sh", [])])
def test_scripts_refuse_while_another_run_holds_the_lock(
    tmp_path: Path, script: str, args: list[str]
) -> None:
    env = _setup(tmp_path)
    with (tmp_path / "res" / ".run.lock").open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        res = _call(script, args, env)
    assert res.returncode == 2
    assert _calls(tmp_path) == []
    assert ".run.lock" in res.stderr


TEST_DB_KEYWORDS = "host=localhost port=55433 dbname=tonomyx user=tonomyx password=tonomyx"


@pytest.mark.parametrize("script,args", [("run_benchmark.sh", ["ban_le"]), ("run_all.sh", [])])
@pytest.mark.parametrize("url", [TEST_DB, TEST_DB_KEYWORDS, "dbname = 'tonomyx' host=h", None])
def test_scripts_refuse_the_test_database(
    tmp_path: Path, script: str, args: list[str], url: str | None
) -> None:
    env = _setup(tmp_path)
    if url is None:
        env.pop("TONOMYX_DATABASE_URL")
    else:
        env["TONOMYX_DATABASE_URL"] = url
    res = _call(script, args, env)
    assert res.returncode != 0
    assert _calls(tmp_path) == []


@pytest.mark.parametrize("url", ["host=localhost dbname=aebench_paper user=tonomyx",
                                 "dbname=tonomyx_paper host=h"])
def test_scripts_accept_a_keyword_dsn_of_another_database(tmp_path: Path, url: str) -> None:
    env = _setup(tmp_path)
    env["TONOMYX_DATABASE_URL"] = url
    res = _call("run_benchmark.sh", ["ban_le"], env)
    assert res.returncode == 0, res.stderr
    assert _subs(tmp_path) == ["run", "report"]
