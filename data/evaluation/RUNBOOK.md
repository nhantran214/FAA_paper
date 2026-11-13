# Paper evaluation runbook (bench_v1)

This is the order in which the lead runs the paper evaluation of sub-project B on the four
paper industries: `ban_le`, `phan_phoi`, `van_tai` and `cntt_phan_mem`. The six other
industries (`san_xuat`, `nha_hang_khach_san`, `y_te`, `giao_duc`, `xay_dung`,
`cho_thue_bds`) are development industries; their cases and the dress-rehearsal configurations
stay in FAA, not in this repository. The rehearsal timings at the end are from that earlier
work, before the baseline arms were replaced by the authors' original code, and they do not
size the guard arms (see "Sizing the guard arms").

**Paper isolation.** The answer side of a paper case is `process.json`, `expected/`,
`attacks.json`, `story.md` and the `title` of `case.meta.json`. Before step 6, no person,
agent or tool opens it. The only exceptions are:

- the case-input drafter and checker (step 3), which read the title, the story opening and
  the input facts and print counts only;
- the expert sheet (step 3), which only people read.

Every command below prints counts and paths only.

**Two machines.** Development, the tests and every timing in this runbook and in
`baselines/README.md` come from the development machine (RTX 5070 Ti, 16 GB of VRAM, shared
with other work). The paper evaluation runs on a separate machine with 48 GB of VRAM: step 0
rebuilds, verifies and probes that machine, and steps 1 to 7 (the engine freeze onward) all run
on it. Plan the run on its probe, not on the numbers here.

## Before you start

- **Every fix lands before the engine freeze.** After step 2, `tonomyx/` and `aebench/`
  (all but `aebench/report/` and `aebench/analysis/`), `baselines/nemo_config/` and
  `baselines/llama_guard_format/` are locked, and so are the five vendored clones (their
  commits and clean state) and the installed Python packages: any change there blocks the
  paper run until a new engine freeze, new sets and new set freezes.
- **One runner per database.** The rule triggers and their state are database-wide, and
  each episode resets the schema `core`. Two experiments, or an experiment and the test
  suite, must never share one database. Give the paper run its own database, for example:

  ```bash
  docker start aebench-postgres
  docker exec aebench-postgres psql -U tonomyx -d tonomyx -c "CREATE DATABASE aebench_paper OWNER tonomyx;"
  export TONOMYX_DATABASE_URL=postgresql://tonomyx:tonomyx@localhost:55433/aebench_paper
  ```

  The test suite (root `conftest.py`) uses `localhost:55433/tonomyx`. Do not run it against
  the paper database.
- **Install the baselines first.** The nine arms need the original baseline code and
  extra models (five in all). On the paper machine this is part of step 0, which also verifies them. From
  the repository root, once per machine:

  ```bash
  .venv/bin/python -m pip install -r requirements-baselines.lock   # exact; see baselines/README.md for the clones
  ollama pull qwen3:14b gpt-oss:20b mistral-small3.2:24b qwen3:30b-a3b llama-guard3:8b
  .venv/bin/python -c "from huggingface_hub import snapshot_download; print(snapshot_download('protectai/deberta-v3-base-prompt-injection-v2'))"
  ```

  The experiment refuses to start when a model it needs is not present: the Ollama models
  by name and digest, the HuggingFace detector by its cached snapshot.
- **Models.** Ollama serves the four digital-employee models (`qwen3:14b`, `gpt-oss:20b`,
  `mistral-small3.2:24b`, `qwen3:30b-a3b`; the benchmark files fix each one's thinking mode),
  `qwen3:14b` also as Progent's policy model and CaMeL's P-LLM and Q-LLM, and `llama-guard3:8b`
  (the `llama-guard` arm). The `agentdojo-defense`
  arm runs `protectai/deberta-v3-base-prompt-injection-v2` in process, on CPU. `nemo-guardrails`
  calls no model. Check Ollama with `curl -s localhost:11434/api/tags`. Drafting uses
  `gemini-3.8-flash`.
- **The Gemini key** goes only into the drafting command's environment. Never print it,
  `cat` its file or write it anywhere:

  ```bash
  set -a; . ~/.config/benchgen/gemini.env; set +a; <command>
  ```

  Run this in a subshell `( ... )` so the key does not stay in your shell.
- `aebench` is `.venv/bin/aebench`. The commands below run from the repository root.

## The order

0. On the paper machine (48 GB of VRAM): rebuild the clones and the venv, verify them and the
   models, set the Ollama server environment, run the probe and size the run. Every later step
   runs on this machine.
1. Commit everything.
2. `aebench freeze engine` on the paper machine, then commit its record.
3. Draft the paper inputs, export the sheet, let people review it, import it, commit
   `data/evaluation/inputs.json`.
4. Draft G-blind and G-informed. Each manifest records `inputs_sha256`.
5. Freeze each set, then commit the sets and their freeze records.
6. Run the paper experiment with the unlock.
7. Report.

The unlock (step 6) checks this order in git, not only in timestamps:

- the engine record, the set records, each set's `manifest.json` and templates, and
  `data/evaluation/inputs.json` are committed and unchanged against HEAD;
- every commit that touched `data/evaluation/freeze/engine.json` comes strictly before
  every commit that added a set record;
- every set records the sha256 of the inputs file it was drafted with, and that file is
  unchanged now.

Nothing may change between step 2 and step 7 in the fingerprinted folders, `tonomyx/`,
`aebench/` (all but `aebench/report/` and `aebench/analysis/`), `baselines/nemo_config/` and
`baselines/llama_guard_format/`, nor in the vendored clones or the installed packages.
Nothing may change in `data/evaluation/inputs.json` after step 4 starts, or in the two sets
after step 5. The run checks the engine, the sets and the inputs file before and after every
episode, and it stops on a change (`FreezeChanged`); the clones and packages are checked with
them. Do not check out another branch in this work tree while the run is going.

### 0. Prepare and verify the paper machine (before step 1)

Do this on the paper machine (48 GB of VRAM) before step 1, from the repository root of a
clone of this repository at the commit to be frozen (every fix landed). Steps 1 to 7 then run
on this machine: the engine freeze (step 2) records this machine's clone HEADs and installed
distributions, and the unlock (step 6) compares them with the machine it runs on. Nothing here
opens a paper case.

1. **Rebuild the clones** with the commands of `baselines/README.md`, section 1, and check
   their commits (each must print the commit shown and an empty status):

   ```bash
   for d in agentdojo camel nemo_guardrails purple_llama progent; do
     echo "$d $(git -C baselines/$d rev-parse HEAD)"; git -C baselines/$d status --short; done
   # agentdojo       089ed468cf3ed0322acc66b0211f26d9d90dbf60
   # camel           f083b6b396399d3b3c7f2ddaf613a5945eaf32d8
   # nemo_guardrails 83d03ad529d2be1399f1dede24be59d4381ee42e
   # purple_llama    172c1074069eb88ec834124272c1b1c4f8893445
   # progent         b02783b896d4bf01a2adf24738015e258db8d35b
   ```

2. **Install the pinned environment** (Python 3.13) and nothing else into it:

   ```bash
   python3.13 -m venv .venv
   .venv/bin/python -m pip install pip==25.2
   .venv/bin/python -m pip install -r requirements-baselines.lock
   ```

   The packages hash of the engine freeze covers every installed distribution, `pip` itself
   included, and `pip freeze` (hence the lock) leaves `pip` out: a venv's bundled `pip` depends
   on the Python release, so pin it to the version the lock was checked with (25.2). Install
   nothing else into this venv, now or later: step 2 records exactly what is installed here.

3. **Models.** Pull the Ollama models and check their digests against the development
   machine's, then download the detector and check its snapshot hash:

   ```bash
   for m in qwen3:14b gpt-oss:20b mistral-small3.2:24b qwen3:30b-a3b llama-guard3:8b; do ollama pull "$m"; done
   curl -s localhost:11434/api/tags | .venv/bin/python -c "import json,sys; [print(m['name'], m['digest']) for m in json.load(sys.stdin)['models']]"
   # qwen3:14b       bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8
   # llama-guard3:8b 46f211c3d8662823ea4956d1a9e92b2924f84cbd0a0f88b64eaadb59fe58b99d
   .venv/bin/python -c "from huggingface_hub import snapshot_download; print(snapshot_download('protectai/deberta-v3-base-prompt-injection-v2'))"
   HF_HUB_OFFLINE=1 .venv/bin/python -c "from huggingface_hub import snapshot_download; print(snapshot_download('protectai/deberta-v3-base-prompt-injection-v2', local_files_only=True).rsplit('/', 1)[1])"
   # 90c9989b1a342275dd0d1a95aad283c04e075671
   ```

   From here on, run every command with `HF_HUB_OFFLINE=1` exported, so nothing can fetch
   another revision of the detector during the run.

   Record all five Ollama digests this machine prints (`curl` above, or `ollama list`, whose
   ID column is the digest's first 12 characters) in this table and commit it with step 1.
   The two known from the development machine must match; the other three are recorded here
   for the first time. Every row also records its model's digest, and the run checks each
   model by name and digest.

   | Model | Role | Digest on the paper machine |
   |---|---|---|
   | `qwen3:14b` | digital employee, `guard_model` (Progent) | |
   | `gpt-oss:20b` | digital employee | |
   | `mistral-small3.2:24b` | digital employee | |
   | `qwen3:30b-a3b` | digital employee | |
   | `llama-guard3:8b` | `llama-guard` arm | |

4. **The Ollama server environment** for the whole run (for the systemd service:
   `sudo systemctl edit ollama`, then `sudo systemctl restart ollama`):

   ```ini
   [Service]
   Environment="OLLAMA_NUM_PARALLEL=1"
   Environment="OLLAMA_CONTEXT_LENGTH=32768"
   ```

   `OLLAMA_NUM_PARALLEL=1` keeps one slot per runner, so no two requests share a model's
   context; `OLLAMA_CONTEXT_LENGTH=32768` is the experiment's `num_ctx` (each request also
   asks for it, and the isolation pre-loads at it). Whatever flash-attention setting
   (`OLLAMA_FLASH_ATTENTION`) the server has, keep it unchanged for the whole run: it changes
   the numerics. Do not restart or upgrade Ollama during the run; every row records the
   server's version (`ollama_version`) and the report lists the versions it saw.

5. **Probe the nine arms with each of the four digital-employee models** on the synthetic
   `tests/engine` world (never a paper case), with the test database of the root `conftest.py`
   (`localhost:55433/tonomyx`, `docker compose up -d`), not the paper one. The probe takes the
   digital employee from `FAA_E2E_MODEL` (default `qwen3:14b`) and its thinking from
   `FAA_E2E_THINK` (`true`, `false` or a level; default `false`). Run it once per model, with
   the benchmarks' think setting, so the paper run is not the first time a model meets the
   nine arms:

   ```bash
   for spec in qwen3:14b=false gpt-oss:20b=low mistral-small3.2:24b=false qwen3:30b-a3b=false; do
     FAA_E2E_MODEL="${spec%=*}" FAA_E2E_THINK="${spec##*=}" HF_HUB_OFFLINE=1 \
       .venv/bin/python -m pytest -o addopts="" -m llm tests/aebench/bridges/test_arms_end_to_end.py
   done
   ```

   Each run writes each arm's isolation time, wall time and tokens to
   `arms_probe-<model>.json` under that run's pytest base temp directory; copy the four files
   out before they are cleaned up. Every arm must pass for every model. Size the run from
   those times (see "Sizing the guard arms"): seconds per episode of each arm and model, times
   cases and sets, plus the isolation time per episode. On 48 GB both Ollama models stay
   resident, so `llama-guard` should not show the swaps of the development probe.

Then go on with step 1 on this machine. Do not move the run to another machine after step 2.

### 1. Commit

```bash
git status --short -- tonomyx aebench baselines/nemo_config baselines/llama_guard_format   # must be empty
for d in agentdojo camel nemo_guardrails purple_llama progent; do
  git -C baselines/$d status --short; done                  # must print nothing
git tag tonomyx-v2-paper
```

The tag marks the engine source commit. `engine.json` is committed after it (step 2) and
records the same engine tree.

`aebench freeze engine` needs a clean, committed tree covering `tonomyx/`, `aebench/` (except
`aebench/report/` and `aebench/analysis/`), `baselines/nemo_config/` and
`baselines/llama_guard_format/`. Untracked or ignored files there count as unclean, except
bytecode caches. Each vendored clone must be present and clean (`git status` empty,
untracked files included).

### 2. Freeze the engine and commit its record

**Take the freeze on the paper machine, after step 0.** It records that machine's clone HEADs
and installed distributions, and the unlock in step 6 refuses on any machine whose clones or
packages differ. A freeze taken on the development machine would make the unlock on the paper
machine refuse.

```bash
.venv/bin/aebench freeze engine          # writes data/evaluation/freeze/engine.json
git add data/evaluation/freeze/engine.json && git commit -m "Freeze the paper engine"
```

- The record holds the fingerprint, the commit and `frozen_at`, and what the baselines run
  on (final ruling I3): `baselines`, the `head` commit and `clean` flag of each vendored
  clone (`agentdojo`, `camel`, `nemo_guardrails`, `purple_llama`, `progent`, read with
  `git -C baselines/<name>`, no network), and `packages_sha256`, the sha256 of the sorted
  `name==version` lines of every installed distribution but the project's own (`aebench`),
  read with `importlib.metadata`. `freeze engine` refuses while a clone is missing or not
  clean. The unlock refuses, and the run stops before an episode (`paper_freeze_ok`), when
  a clone's head or clean flag or the packages hash differs from the record. A
  `pip install` or a `git checkout` in a clone after this step blocks the run.
- **Commit the record now, on its own, before any set is frozen.** The unlock refuses a
  set record committed before or together with the engine record. If the engine is ever
  frozen again (`--replace`), draft and freeze new sets under new names.
- **Committing `data/evaluation/freeze/` is the audit trail.** Commits outside the engine
  folders are allowed after the freeze. The unlock checks that the frozen commit is an
  ancestor of HEAD with the same engine tree.
- **From this step until the report, history must stay linear: no merge commits.**
  Use only `git pull --ff-only` / `git merge --ff-only`, and run step 6 on the branch
  where steps 2–5 were committed. A merge commit after the set records are committed
  (including the merge a plain `git pull` makes when the other machine has pushed)
  makes the unlock refuse for good for those set names. The only recovery is
  `freeze engine --replace` and drafting both sets again under new names. If the
  other machine has pushed, rebase or fast-forward before step 2, not after.

### 3. Inputs of the paper cases: draft, export, review, import

`data/evaluation/inputs.json` is outside the engine fingerprint, so the review may take
place after the engine freeze. **The people who review the inputs sheet do not change
`tonomyx/` or `aebench/`.**

What it may read:

- The drafter and the checker read the title, the story opening (before `## Diễn biến`),
  `roles.csv`, `data/*.csv` and the input facts of `process.json`. They print counts only.
- The sheet holds the title and the story opening. **People review it. Agents never open
  it.** Keep it outside the repository, or at least never stage it.

The paper case ids come from `coverage.json`, ids only:

```bash
PAPER_CASES=$(.venv/bin/python -c "import json; rows=json.load(open('data/bench_v1/coverage.json'))['rows']; print(' '.join('--case '+r['case_id'] for r in rows if r['industry'] in {'ban_le','phan_phoi','van_tai','cntt_phan_mem'}))")
( set -a; . ~/.config/benchgen/gemini.env; set +a; .venv/bin/aebench inputs $PAPER_CASES draft --model gemini-3.8-flash --seed 1 )
.venv/bin/aebench inputs $PAPER_CASES check
.venv/bin/aebench inputs $PAPER_CASES export --out ~/paper-inputs-sheet.csv
# people review the sheet (decision approve/reject, corrections, reviewer)
.venv/bin/aebench inputs import --sheet ~/paper-inputs-sheet.csv
.venv/bin/aebench inputs $PAPER_CASES check   # every paper case approved, flagged=0
git add data/evaluation/inputs.json && git commit -m "Reviewed paper inputs"
```

- `--seed 1` is recorded in the manifest, but Gemini does not honour it: drafting is not
  reproducible bit for bit. The committed file is the record.
- `check` flags:
  - outcome words (for example `duyệt`, `từ chối`); the drafter's prompt lists them;
  - long copies of the story, and length;
  - a request that quotes the value of a candidate input fact its allow-list does not
    hold (`quotes un-listed fact NAME`).

  A flagged request needs a reviewer's correction (add the fact to
  `corrected_input_facts`, or reword the request), or an `override_reason`.
- The allow-list decides only what a step is shown. Every whole-number input fact the run
  reaches is a money source for platform rule 3 whatever the list, so an amount quoted in
  a request is never refused for want of a source.
- **The people review checks that each request carries the quantities and other facts
  the requester would know**, as an input fact or in the request text. A digital employee
  cannot make a document whose lines it was never told: the development request
  CASE-V1-0001, for example, omits the ordered quantity its first document needs. Add only
  what the requester would know; never the document type, document ids, an approval
  outcome or a flag.
- A sheet cell that starts with `=`, `+`, `-` or `@` is written with a leading `'`, so a
  spreadsheet never runs it as a formula. The import takes the `'` off again.
- The import prints `unknown_case_ids=N` for sheet rows the inputs file does not hold.
  Such rows are skipped.
- The import keeps a row as `draft` when its decision is missing. A paper experiment
  refuses any case whose inputs are not `approved`.
- Commit `data/evaluation/inputs.json`. Never commit the sheet. Do not change the inputs
  file after step 4 starts: the sets record its sha256, and the unlock compares.

### 4. Draft G-blind and G-informed over the four paper industries

```bash
PAPER="ban_le phan_phoi van_tai cntt_phan_mem"
( set -a; . ~/.config/benchgen/gemini.env; set +a; .venv/bin/aebench draft --mode blind --industries $PAPER --name g-blind-paper --model gemini-3.8-flash --seed 1 )
( set -a; . ~/.config/benchgen/gemini.env; set +a; .venv/bin/aebench draft --mode informed --industries $PAPER --name g-informed-paper --model gemini-3.8-flash --seed 1 )
```

`--seed 1` is recorded in each manifest, but Gemini does not honour it, so drafting is not
reproducible bit for bit. The frozen set is the record.

What it may read:

- **Blind:** the process names of `axes.json`, the step vocabulary, the platform rules and a
  toy format example. No case knowledge.
- **Informed:** additionally, per case of the four industries:
  - `roles.csv`, `policy.json`, `kb/*.md` and `data/*.csv`;
  - its coverage row and its approved neutral request;
  - `case.meta.json`, opened by `company_pack_from_case` only for the case id and the
    generator version (the pack's name and version), never the title. Neither reaches
    the prompt; companies are labelled `Công ty N` (ruling R9e).

  It never opens `story.md`, `process.json`, `expected/` or `attacks.json`. Informed
  drafting refuses when any paper case lacks approved inputs.

Each set must be drafted after the engine freeze and on the frozen engine. Its manifest
records:

- the engine fingerprint;
- `started_at` and `drafted_at`, with microseconds;
- `inputs_sha256`, the sha256 of `data/evaluation/inputs.json` at drafting.

If the engine changes during drafting, the set is marked invalid and can never be frozen.
A hosted call may take `--timeout` seconds (default 900). A hosted answer of 400, 413 or
422 stops the command with `ModelUnavailable`, since the same request would be refused
again; 429 and 5xx answers are retried.

The command prints one line per process (`valid` or `invalid`, with the rounds used). An
invalid process has no usable template. Its cases are `not_run` ("the set marks this
template invalid"), and the report's governance size counts only valid templates. Record
the counts.

### 5. Freeze each set and commit

```bash
.venv/bin/aebench freeze set data/evaluation/governance/g-blind-paper
.venv/bin/aebench freeze set data/evaluation/governance/g-informed-paper
git add data/evaluation/governance/g-blind-paper data/evaluation/governance/g-informed-paper data/evaluation/freeze/sets/
git commit -m "Freeze the paper governance sets"
```

- The freeze writes `set_hash`, `frozen_at` and a digest of the manifest into the set. It
  also writes a separate record under `data/evaluation/freeze/sets/`, which is never
  overwritten.
- `freeze set` prints `valid=N total=M`: how many of the set's processes drafted a valid
  template.

### 6. Run the paper experiment with the unlock

The experiment is four per-industry benchmarks, one file each in `experiments/v2/benchmarks/`
(`ban_le.json`, `phan_phoi.json`, `van_tai.json`, `cntt_phan_mem.json`; experiment names
`bench-<industry>`). They share one protocol: `"paper": true`, the two frozen paper sets, all
nine arms, the four digital-employee models (`qwen3:14b`, `gpt-oss:20b` with thinking `"low"`,
`mistral-small3.2:24b`, `qwen3:30b-a3b`; the other three with thinking off), `guard_model`
`"qwen3:14b"` (used by `progent` only: every other guard arm has a model fixed by the arm,
`llama-guard3:8b` for `llama-guard`, the HuggingFace detector for `agentdojo-defense`, and none
for `nemo-guardrails` and `camel-capability`, whose own models are the digital employee's),
temperature 0, seed 1, `num_ctx` 32768, one repetition. Each selects its own industry's cases
with the statuses `["approved"]`: the paper runs on expert-approved cases only
(`cases.statuses` filters on the `status` of `case.meta.json`, not on the inputs status), so
`aebench cases` prints 0 cases until the review ends. Do not edit the files for the run.

Size the run before starting:

```bash
.venv/bin/aebench cases                          # cases per benchmark, missing folders, episodes
.venv/bin/aebench cases --statuses draft_v1      # a preview with the draft cases
```

Episodes per repetition = cases x 9 arms x 2 sets x 4 models; `aebench cases` prints the
total as `episodes_per_repetition`. Turn it into hours with the seconds per episode of each
arm from the step 0 probe (see "Sizing the guard arms"), per model: the four models differ in
size and speed, and `qwen3:30b-a3b` and `mistral-small3.2:24b` are the slowest to load.

Before starting, check that this machine still matches the engine freeze (the unlock checks
it too; this only fails earlier and with a clearer message):

```bash
.venv/bin/python -c "from tonomyx.bench.freeze import check_environment, read_engine_freeze; check_environment(read_engine_freeze()); print('clones and packages match the engine freeze')"
```

Then:

```bash
export TONOMYX_DATABASE_URL=postgresql://tonomyx:tonomyx@localhost:55433/aebench_paper
export HF_HUB_OFFLINE=1   # the detector comes from the verified local snapshot only (step 0)
mkdir -p results/v2
( setsid nohup scripts/run_all.sh > results/v2/run_all.log 2>&1 & echo $! > results/v2/run_all.pid )
```

Keep the parentheses. Inside the subshell there is no job control, so `setsid` does not fork
and `$!` is the new session's leader: its PID is the process group of the whole run. Run
without them from an interactive shell, `setsid` forks and `$!` names a parent that has
already exited.

To stop the run (the script, its `run_benchmark.sh` and the `aebench` process), kill the
whole process group, then run `scripts/run_all.sh` again later to resume:

```bash
kill -- -"$(cat results/v2/run_all.pid)"
```

`scripts/run_all.sh` runs `scripts/run_benchmark.sh` for `ban_le`, `phan_phoi`, `van_tai` and
`cntt_phan_mem` in that order, then the paper artefacts (step 7). Each benchmark runs
`aebench run experiments/v2/benchmarks/<industry>.json --out results/v2` (log appended to
`results/v2/bench-<industry>.log`) and writes its report (step 7). Both scripts take an
exclusive lock on `results/v2/.run.lock` and refuse to start while another run holds it. They
refuse an unset `TONOMYX_DATABASE_URL` and the test database (a URL ending in `/tonomyx`, or a
keyword DSN with `dbname=tonomyx`). To run one benchmark alone: `scripts/run_benchmark.sh
<industry>`, or `.venv/bin/aebench run experiments/v2/benchmarks/<industry>.json`.

Exit codes and what the scripts do with them:

| Exit | Meaning | `run_benchmark.sh` | `run_all.sh` |
|---|---|---|---|
| 0 | done | writes the report | next benchmark |
| 1 | done, but some rows have status `error` | writes the report, warns with the count, exits 1 | next benchmark; after the paper artefacts, exits 1 listing the benchmarks with error rows |
| 2 | refused | stops | stops |
| 3 | the model server went away | retries (below); stops with 3 if it gives up | stops |
| other | `aebench exited N (unexpected)` (a signal such as 130 or 143, or a Python failure) | stops | stops |

Retries on exit 3: `MAX_RETRIES` (default 5) is the number of retries after the first
attempt, `RETRY_SLEEP` (default 60) the seconds between them. The count starts again whenever
the results file grew since the previous attempt, so a long run survives repeated transient
drops and gives up only after `MAX_RETRIES` retries in a row without a new row.

**Exit 1, error rows.** An `error` row is an episode that raised an exception the run caught;
the report counts it as a failure of its arm (not perfect), so an infrastructure error left in
place silently penalises that arm. When a benchmark ends with exit 1:

1. Inspect the error rows: their `reason` is the exception type (counts only, no case text):

   ```bash
   .venv/bin/python -c "import json,sys,collections; rows={}; [rows.__setitem__(r['episode_id'], r) for r in map(json.loads, open(sys.argv[1]))]; print(collections.Counter((r['arm'], r.get('reason')) for r in rows.values() if r['status']=='error'))" results/v2/bench-ban_le.jsonl
   ```

2. Fix the cause (a server, a resource). A cause in the frozen engine cannot be fixed after
   step 2: stop and decide with the lead.
3. Run again with `RETRY_ERRORS=1` (`aebench run --retry-errors`): the episodes whose last row
   is an error run again, the new row is appended, and the report keeps the last row of each
   episode:

   ```bash
   ( RETRY_ERRORS=1 setsid nohup scripts/run_all.sh > results/v2/run_all.log 2>&1 & echo $! > results/v2/run_all.pid )
   ```

4. Error rows left in place count as failures in the report and the paper artefacts; say so in
   the paper if any remain.

- The run issues the unlock in its own process (`unlock_paper` against
  `data/evaluation/freeze/engine.json`, the repository's own record, and the two sets). It
  refuses before touching any answer when:
  - the engine is not clean or not the frozen one, or a vendored clone or the installed
    packages differ from the engine record;
  - a set is not frozen, does not verify or was drafted before the freeze;
  - a freeze file (engine record, set records, set manifests and templates, inputs file)
    is not committed, or differs from HEAD;
  - a set record was committed before or with the engine record;
  - the inputs file is not the one the sets were drafted with;
  - a case lacks approved inputs, a case folder is missing, or a case is of a
    development industry.
- The rows go to `results/v2/bench-<industry>.jsonl`. Paper rows carry counts only, with no scorer
  text. Each row records `inputs_sha256`.
- Exit code 3 (`stopped: ...`) means a model server went away. The scripts retry it; if it
  persists, fix the server and run `scripts/run_all.sh` again: the run resumes, and the
  finished episodes are kept. Exit code 2 is a refusal. Exit code 1 means some rows are
  `error` (see "Exit 1, error rows" above).
- Each episode starts from a clean Ollama server: before it, the run unloads the Ollama
  models the episode uses (`keep_alive: 0`), waits until `/api/ps` lists none, then loads them
  again with a bare load request at the experiment's `num_ctx` and waits until each is listed
  (`aebench/run/isolation.py`). Unload and pre-load are outside the row's `wall_s` and latency
  figures, and the episode's first request does not relaunch the runner. Only on a GPU that
  cannot hold both of an arm's models (`llama-guard` on the 16 GB development GPU; not on the
  48 GB paper machine) is the guard model swapped in inside the episode, with the digital
  employee's model the one left loaded. The server reuses cached KV prefixes across requests,
  which can change a greedy model's reply to a byte-identical request, so without this an
  arm's results would depend on what ran before it. Rows record `ollama_isolated: true` and
  `ollama_version`. If the unload fails or times out (60 s) the run stops with exit code 3;
  run it again to resume.
- Keep the logs, the PID file and `.run.lock` out of git.

### 7. Report

`scripts/run_benchmark.sh` writes each benchmark's report when its run is done, and
`scripts/run_all.sh` then writes the paper artefacts. To redo either by hand:

```bash
.venv/bin/aebench report results/v2/bench-ban_le.jsonl --out results/v2/bench-ban_le   # per benchmark
.venv/bin/aebench paper-artefacts results/v2/bench-ban_le.jsonl results/v2/bench-phan_phoi.jsonl \
  results/v2/bench-van_tai.jsonl results/v2/bench-cntt_phan_mem.jsonl --out results/v2/paper
```

`aebench paper-artefacts` writes the paper's tables and figures to `results/v2/paper/`
(aggregates only; the root `README.md` lists each file). Each benchmark's report writes
`report.md`, `summary.csv`, `mcnemar.csv` and `defence.csv`, with one cell per arm, set and
model:

- **Number 1** (perfect share) is also split by whether the run's role mapping was exact,
  beside the share of exact mappings.
- **Number 2** (safe share) stands beside `unsafe_or_unmapped`, the share of attack
  episodes in which a forbidden effect happened or the run wrote an approval or payment
  that maps to no case row. A forbidden effect on such a row escapes the invariants, so
  the unsafe share lies between the two.
- **Number 4** adds the platform's own time (`wall_s` less the model and guard latency)
  and the guard latency, beside the paired `wall_s` difference against `bare`.
- **Defence diagnostics** sum the counters of the baseline bridges per cell
  (`pi_detections`, `pi_errors`, `progent_errors`, `llama_guard_unreadable`,
  `camel_program_errors`, `camel_policy_denials`, `camel_no_outcome`). Read them before the numbers: a `*_errors`
  count above zero means a detector or guard failed and let the call or message through,
  and a high `camel_program_errors` or `camel_no_outcome` means CaMeL's score reflects the
  14B model failing to write a runnable program, not the policy engine. No case id or case
  text appears in them.

The 95% Wilson intervals of the CSVs treat episodes as independent. They are not quite:
episodes cluster by case (the same case runs under every model and both sets), so the
intervals are somewhat too narrow, and the paper's methods section must say so.

A paper report refuses development rows, rows without `freeze_ok`, and rows of more than
one engine; `aebench paper-artefacts` also refuses rows none of which is a paper row. Only `aebench/report/` and `aebench/analysis/` may change after the run, and
only to re-report. Commit the report files. Commit the JSONL if it is under 20 MB;
otherwise keep it with the release artefacts and record its sha256 in the commit message.

## Sizing the guard arms

Before the paper run, time the arms in a probe on the paper machine (step 0): a few
synthetic episodes per arm (the `tests/engine` fixtures), never paper cases. Record the seconds per
episode of each arm and plan the paper run on those, not on the rehearsal numbers below. The
probe is needed because:

- the guard arms now run the authors' original code, and the numbers below were measured with
  the earlier re-implemented guards;
- `progent` makes at least one policy-model call per step plus one per tool result (one policy
  generation took 82 s at about 5000 prompt tokens on the development machine while its GPU
  was contended);
- `camel-capability` makes up to 10 P-LLM attempts per step plus Q-LLM calls (one real run took
  about 1465 s on the development machine);
- on the 16 GB development GPU `llama-guard3:8b` and `qwen3:14b` do not fit together, so
  Ollama swaps them between calls; on the 48 GB paper machine both stay resident, so the
  development numbers overstate the `llama-guard` arm;
- the `agentdojo-defense` detector runs on CPU with torch capped at `min(8, cpu_count)` threads
  (0.34 s per call on the development machine), so its latency depends on the machine's CPU.

On the development machine, per-episode isolation (unload and pre-load) took 2.5 to 3.9 s for
an arm with one Ollama model and 7.0 s for the two-model arm (qwen3:14b and llama-guard3:8b),
outside the row's `wall_s`: there it adds about 4 s per episode (the episodes per repetition from `aebench cases` times about 4 s). Use the isolation times of the step 0 probe for the paper machine.

Timings measured during development of the baselines were taken on the development machine,
often while its GPU was contended, and are not representative. A first probe of all nine arms
on one synthetic episode each (2026-11-13, on the development machine) is in
`baselines/README.md`, "Sizing probe". It is a lower bound: the synthetic case is small. Repeat
it on the paper machine (step 0), with more episodes if time allows, before planning the
paper run.

## Sizing from the rehearsal (earlier work)

The development rehearsals used the same arms, model and sampling as the paper run, on
development cases, with the earlier re-implemented guard arms. The paper run has
9 arms × 2 sets × cases × repetitions episodes. All the numbers below are measured with
qwen3:14b, think off, on the development machine (RTX 5070 Ti, 16 GB), on 2026-11-11.

| Run | Engine | Episodes | Rows | Wall time | s/episode |
|---|---|---|---|---|---|
| Rehearsal 1 (`dev-rehearsal`, Task 13) | before the Task 15 fixes | 1152 = 64 cases × 9 × 2 | 1134 scored, 18 not_run, 0 error | 1 h 53 m | 5.9 (max 23) |
| Rehearsal 2 (`dev-rehearsal-2`) | Task 15 fixes, before the read-enum fix | 576 = 32 cases (one per process) × 9 × 2 | 567 scored, 9 not_run, 0 error | 1 h 21 m | 8.4 (median 6.5, max 57) |
| Probe 3 | final Task 15 engine | 54 = 3 cases × 9 × 2 | 54 scored | 11 m 38 s | 12.9 (median 11.6, max 27) |

- **Time grows as episodes go further.** In rehearsal 1, 90% of the episodes stopped at the
  first digital-employee step, so 5.9 s/episode is too low. The same three probe cases
  took 6.0 s/episode before the fixes and 12.9 s/episode after them.
- **Plan the paper run on at least 13 s per scored episode**, so 1000 episodes take about
  3.6 h. Leave more room still: episodes that run further take longer, and the guard arms
  take about 1.5 to 3 times as long as `full`.
- **Not-run episodes** take under 1 s. These are templates that do not bind to the
  company.
- **Drafting, G-blind.** About 1 minute per process type: 32 processes in 21 minutes.
- **Drafting, G-informed.** 68 minutes for the development set. A process whose companies
  cannot all be bound can use all 4 rounds, about 30 minutes on its own.
- **Rehearsal 2 predates the read-enum fix** (Task 15 review I1). Until then,
  `read_records` listed every readable table, even where the step's token reads fewer.
  - In rehearsal 2, 36 first-step stops (18 in `full`, 18 in `no-database`) were reads
    refused as outside the token's read scope. Such a refusal ends the step.
  - The token-off arms never meet this refusal, so rehearsal 2's `full` and `no-database`
    cells may understate those arms.
  - Probe 3, on the final engine, has no such stop.

## Known issues from the rehearsal

**Early stops at the first document (finding F7) and their fix (Task 15).**

- **The finding.** In rehearsal 1, 1025 of the 1134 scored episodes (90.4%) stopped at the
  first digital-employee step. The diagnosis attributed 918 of the 1025 to the platform:
  - no `loai_ct` vocabulary reached the model, and it copied the step's `doc` label
    instead;
  - a `chung_tu` draft scope without `dong_ct`;
  - no table or column names were shown;
  - a create step could not read item or partner codes;
  - `search_kb` did not match article codes;
  - and the prompt said "adjust after a refusal", although a refused call ends the step.
- **The fix.**
  - The schemas now list the document types, the `record_event` kinds, and the tables
    with their columns (`read_records` lists only the step's readable tables).
  - The line's `ma_hh` is described as an optional `hang_hoa` code.
  - A `chung_tu` draft scope also drafts `dong_ct`.
  - Create steps may read records.
  - `search_kb` matches `ma_kb`.
  - The prompt says a refused call ends the step.
- **The effect.**
  - On the same 32 cases, first-step stops fell from 89.4% (rehearsal 1) to 63.8%
    (rehearsal 2).
  - On the three probe cases they fell from 100% to 38.9% (probe 3), and 11 of those 54
    episodes reached the end of the run or a wait.
- **Numbers 1 and 2 do not yet tell the arms apart.** Number 1 is 0 in every cell of both
  rehearsals, and number 2 is 1.0 in every cell (2 attack episodes per cell in
  rehearsal 2). The development rehearsals test the pipeline, not the arms.
- **Remaining stops are mostly the model or the data.**
  - The model sometimes sends a `loai_ct` outside the listed codes, since Ollama does not
    enforce schema enums.
  - It writes `don_gia: 0` instead of leaving an unknown price empty (refused by rule 3).
  - It sends a line without `so_luong`.
  - Guards block a call the step needs.
  - The digital employee refuses when the request lacks facts (see the data notes).
- **The `ung_vien` binding.** The g-blind-dev recruitment template's `ung_vien` role binds
  to no company role, so its cases are `not_run`. Rehearsal 2 has 9 such rows: CASE-V1-0065
  × 9 arms.
- **Knowledge-base exposure changed.** `search_kb` now finds an article by its code. A
  kb-channel attack case whose request names the article's code therefore reaches the
  article where it did not before. Keep this in mind when comparing rehearsals 1 and 2.

Data notes (Task 15; no engine change; they count against the run as measured):

- **Requests missing facts.** A request that lacks a quantity or other fact the first
  document needs now stops the run. CASE-V1-0001 (dev) gives no ordered quantity, and the
  digital employee refuses at the order or the budget check. The people review of the
  paper inputs (step 3) checks this.
- **Blind templates with person steps the case cannot play.** A blind template can hold
  a person or outside step that the case's environment cannot play
  (`step … was skipped, and it is not optional`). In each rehearsal, 4.8% of all scored
  rows stopped there before any digital-employee step, all of them g-blind rows (54 in
  rehearsal 1, 27 in rehearsal 2; vendor_onboarding, cash_advance, bank_reconciliation).
  This counts against G-blind as measured.
- **Template read scopes narrower than the step.** A drafted role scope can lack a table
  its own step needs. For example, a g-informed-dev onboarding check needs `ho_so`, but
  the role's `scope.read` does not hold it. The model is no longer shown such a table, so
  the step goes without it.
- **Invented ids at approval steps.** The model sometimes calls `request_approval` or
  `notify` with ids it made up (the case id as `ma_ct`, a template label as `ma_pd`),
  instead of the document it created. The platform refuses this correctly.

Other:

- **Informed drafting is slow.** Repair rounds on `gemini-3.8-flash` took 4 to 10 minutes,
  and the development set took 68 minutes. `aebench draft` waits up to `--timeout` seconds
  (default 900) per call.
