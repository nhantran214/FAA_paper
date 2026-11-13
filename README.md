# FAA_paper: the paper's copy of TonomyX

This repository is the paper's own copy of the engine (`tonomyx/`) and the evaluation harness
(`aebench/`), used to test **framed autonomy by architecture** against four published defences
and Progent on four per-industry benchmarks. `baselines/README.md` describes the baselines (the
authors' original code, reached through thin bridges). The full protocol is
`data/evaluation/RUNBOOK.md`.

## 1. Requirements

- A machine with a 48 GB GPU for the paper run (a 16 GB GPU runs the tests and small trials).
- Docker (PostgreSQL), Ollama, and Python 3.13.

## 2. Setup

The paper machine is prepared and verified by RUNBOOK step 0 (clones, pinned venv, models,
HuggingFace snapshot, Ollama environment, end-to-end probe). The commands:

```bash
docker compose up -d                       # PostgreSQL on port 55433
python3.13 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,analysis]'
# the clones of baselines/ first (baselines/README.md, section 1), then the pinned baselines:
.venv/bin/python -m pip install -r requirements-baselines.lock   # or: -r requirements-baselines.txt
for m in qwen3:14b gpt-oss:20b mistral-small3.2:24b qwen3:30b-a3b llama-guard3:8b; do ollama pull "$m"; done
.venv/bin/python -c "from huggingface_hub import snapshot_download; print(snapshot_download('protectai/deberta-v3-base-prompt-injection-v2'))"
```

For the paper run, install from the lock file only, as RUNBOOK step 0 says.

## 3. Benchmarks

One benchmark per industry. Each runs 9 arms, 2 frozen governance sets and 4 digital-employee
models (`qwen3:14b`, `gpt-oss:20b`, `mistral-small3.2:24b`, `qwen3:30b-a3b`), on the cases whose
`status` is `approved`.

| Industry | Experiment file | Command | Results file |
|---|---|---|---|
| `ban_le` | `experiments/v2/benchmarks/ban_le.json` | `scripts/run_benchmark.sh ban_le` | `results/v2/bench-ban_le.jsonl` |
| `phan_phoi` | `experiments/v2/benchmarks/phan_phoi.json` | `scripts/run_benchmark.sh phan_phoi` | `results/v2/bench-phan_phoi.jsonl` |
| `van_tai` | `experiments/v2/benchmarks/van_tai.json` | `scripts/run_benchmark.sh van_tai` | `results/v2/bench-van_tai.jsonl` |
| `cntt_phan_mem` | `experiments/v2/benchmarks/cntt_phan_mem.json` | `scripts/run_benchmark.sh cntt_phan_mem` | `results/v2/bench-cntt_phan_mem.jsonl` |

The cases are still under review, so their number changes: `.venv/bin/aebench cases` prints the
cases of each benchmark, and `.venv/bin/aebench cases --statuses draft_v1` previews with the
draft cases. The cases
are currently in Vietnamese. The published benchmark will be in English; the translation is
pending.

## 4. Run everything

```bash
export TONOMYX_DATABASE_URL=postgresql://tonomyx:tonomyx@localhost:55433/aebench_paper   # the paper database
export HF_HUB_OFFLINE=1
scripts/run_all.sh
```

`scripts/run_all.sh` runs the four benchmarks in order, writes each benchmark's report, and then
runs `.venv/bin/aebench paper-artefacts`. For the long paper run, start it in its own process
group and stop it by killing the group (RUNBOOK step 6):

```bash
( setsid nohup scripts/run_all.sh > results/v2/run_all.log 2>&1 & echo $! > results/v2/run_all.pid )
kill -- -"$(cat results/v2/run_all.pid)"   # to stop the run; keep the parentheses above
```

- The scripts refuse an unset `TONOMYX_DATABASE_URL` and the test database (a URL ending in
  `/tonomyx` or a keyword DSN with `dbname=tonomyx`); create the paper database as in the
  RUNBOOK ("Before you start"). They take a lock on `results/v2/.run.lock` and refuse to start
  while another run holds it.
- The run resumes: run the same command again and the finished episodes are skipped.
- A model server that goes away (exit 3) is retried: `MAX_RETRIES` (default 5) retries,
  `RETRY_SLEEP` (default 60) seconds apart, and the count starts again whenever a new row was
  written since the previous attempt.
- A benchmark that ends with `error` rows (exit 1) still gets its report, and `run_all.sh`
  goes on with the next benchmark, then exits 1 naming the benchmarks with error rows. An
  error row counts as a failure in the report, so do not leave infrastructure errors in place:
  read the error rows' `reason` (the exception type), fix the cause, and run again with
  `RETRY_ERRORS=1 scripts/run_all.sh`, which re-runs the episodes whose last row is an error
  (RUNBOOK step 6, "Exit 1, error rows").
- A refusal (exit 2), a server still gone after the retries (exit 3) or any other exit stops
  the run.

Size: episodes per repetition = cases x 9 arms x 2 sets x 4 models. `.venv/bin/aebench cases` prints
`episodes_per_repetition`; turn it into hours with the timings of the RUNBOOK step 0 probe.
A paper run also needs the freeze and unlock steps of the RUNBOOK (steps 1 to 5) first.

## 5. Outputs

Each benchmark writes `results/v2/bench-<industry>/` with `report.md`, `summary.csv`,
`mcnemar.csv` and `defence.csv`. `.venv/bin/aebench paper-artefacts` writes `results/v2/paper/`
(aggregates only; rates carry 95% Wilson intervals). The Wilson intervals treat episodes as
independent, although episodes cluster by case (one case runs under every model and both sets);
the paper's methods section must say so. The command refuses rows none of which is a paper
row. Each table is a `.csv` and a `.tex`
(tabular body, booktabs, no caption); each figure is a `.pdf` and a `.csv` of its data.

| File | Shows |
|---|---|
| `tab_fidelity` | perfect share per arm, set and benchmark (and all), McNemar against `full` on perfect (Holm) |
| `tab_safety` | safe share and `unsafe_or_unmapped` on attack cases, McNemar against `full` on the safety outcome (Holm) |
| `tab_false_refusal` | share of legitimate work wrongly blocked, per arm, set and benchmark |
| `tab_cost` | per arm, median model and guard tokens and median wall, platform and guard-latency seconds |
| `tab_defence` | the baseline bridges' diagnostic counters per arm |
| `tab_models` | perfect and safe share per digital-employee model and arm |
| `fig_benchmarks` | perfect share per arm for each benchmark and all |
| `fig_fidelity_safety` | scatter of perfect share against safe share, per arm and model |
| `fig_cost` | scatter of median wall time against perfect share, per arm |

## 6. Tests

```bash
.venv/bin/python -m pytest -o addopts="" -q            # the full suite (needs the database from section 2)
.venv/bin/python -m pytest -o addopts="" -q -m llm     # opt-in: tests that call a live local model
```

Never run the tests against the paper database: both reset the schema `core`.
