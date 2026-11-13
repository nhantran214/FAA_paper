#!/usr/bin/env bash
# Run the four paper benchmarks in order, then the paper artefacts.
# Env:  AEBENCH, MAX_RETRIES, RETRY_SLEEP, RETRY_ERRORS, RESULTS_DIR (default results/v2),
#       TONOMYX_DATABASE_URL (see run_benchmark.sh).
# Lock: holds an exclusive lock on $RESULTS_DIR/.run.lock for the whole run and refuses when
#       another run holds it.
# A benchmark that ends with error rows (exit 1) does not stop the run: the next benchmark
# and the paper artefacts still run. A refusal (2), a model server still gone after the
# retries (3) or an unexpected exit stops it.
# Exit: 0 done; 1 done, but the benchmarks listed at the end have error rows; otherwise the
#       code of the benchmark or command that stopped the run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

AEBENCH="${AEBENCH:-.venv/bin/aebench}"
RESULTS_DIR="${RESULTS_DIR:-results/v2}"
export AEBENCH RESULTS_DIR

mkdir -p "$RESULTS_DIR"
exec 9>"$RESULTS_DIR/.run.lock"
if ! flock -n 9; then
  echo "refused: another run holds $RESULTS_DIR/.run.lock; wait for it or stop it first" >&2
  exit 2
fi
export AEBENCH_RUN_LOCK_HELD=1

with_errors=()
for industry in ban_le phan_phoi van_tai cntt_phan_mem; do
  rc=0
  scripts/run_benchmark.sh "$industry" || rc=$?
  case "$rc" in
    0) ;;
    1)
      with_errors+=("$industry")
      echo "run_all: $industry has error rows; continuing with the next benchmark" >&2
      ;;
    2) echo "run_all: $industry refused (exit 2); stopping" >&2; exit 2 ;;
    3) echo "run_all: $industry stopped, model server gone after the retries (exit 3); stopping" >&2; exit 3 ;;
    *) echo "run_all: $industry exited $rc (unexpected); stopping" >&2; exit "$rc" ;;
  esac
done

"$AEBENCH" paper-artefacts \
  "$RESULTS_DIR/bench-ban_le.jsonl" \
  "$RESULTS_DIR/bench-phan_phoi.jsonl" \
  "$RESULTS_DIR/bench-van_tai.jsonl" \
  "$RESULTS_DIR/bench-cntt_phan_mem.jsonl" \
  --out "$RESULTS_DIR/paper"

if [ "${#with_errors[@]}" -gt 0 ]; then
  echo "run_all: done, but these benchmarks have error rows (each counts as a failure): ${with_errors[*]}; fix the cause and run again with RETRY_ERRORS=1" >&2
  exit 1
fi
