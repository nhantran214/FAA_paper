#!/usr/bin/env bash
# Run one paper benchmark (resuming, with retries), then write its report.
# Usage: scripts/run_benchmark.sh <ban_le|phan_phoi|van_tai|cntt_phan_mem>
# Env:   AEBENCH       the aebench command (default .venv/bin/aebench)
#        MAX_RETRIES   retries after the first attempt while the run stops on exit 3, the
#                      model server gone (default 5; attempts = MAX_RETRIES + 1). The count
#                      starts again whenever the results file grew since the previous
#                      attempt, so only drops without progress use it up.
#        RETRY_SLEEP   seconds between retries (default 60)
#        RETRY_ERRORS  1 to run again the episodes whose last row is an error
#                      (aebench run --retry-errors), after their cause is fixed
#        RESULTS_DIR   where logs, results and reports go (default results/v2)
#        TONOMYX_DATABASE_URL  must name the paper database, never the test one (tonomyx)
# Lock:  takes an exclusive lock on $RESULTS_DIR/.run.lock and refuses when another run
#        holds it (run_all.sh holds it for its benchmarks and sets AEBENCH_RUN_LOCK_HELD=1).
# Exit:  0 done; 1 done, but some rows have status error (the report is written; each error
#        row counts as a failure in it); 2 refused; 3 model server still gone after
#        MAX_RETRIES retries without progress; other codes: aebench exited unexpectedly.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

AEBENCH="${AEBENCH:-.venv/bin/aebench}"
MAX_RETRIES="${MAX_RETRIES:-5}"
RETRY_SLEEP="${RETRY_SLEEP:-60}"
RETRY_ERRORS="${RETRY_ERRORS:-0}"
RESULTS_DIR="${RESULTS_DIR:-results/v2}"
INDUSTRIES="ban_le phan_phoi van_tai cntt_phan_mem"

url="${TONOMYX_DATABASE_URL:-}"
if [ -z "$url" ]; then
  echo "refused: TONOMYX_DATABASE_URL is not set (point it at the paper database)" >&2
  exit 2
fi
# The test database is "tonomyx", as a URL path (postgresql://.../tonomyx) or as a keyword
# DSN (dbname=tonomyx).
kw_test_db="(^|[[:space:]])dbname[[:space:]]*=[[:space:]]*'?tonomyx'?([[:space:]]|$)"
if [ "${url%%\?*}" = "${url%/*}/tonomyx" ] || [[ "$url" =~ $kw_test_db ]]; then
  echo "refused: TONOMYX_DATABASE_URL names the test database (tonomyx); use the paper database" >&2
  exit 2
fi

industry="${1:-}"
case " $INDUSTRIES " in
  *" $industry "*) [ -n "$industry" ] || { echo "usage: $0 <${INDUSTRIES// /|}>" >&2; exit 2; } ;;
  *) echo "usage: $0 <${INDUSTRIES// /|}>" >&2; exit 2 ;;
esac

mkdir -p "$RESULTS_DIR"
if [ -z "${AEBENCH_RUN_LOCK_HELD:-}" ]; then
  exec 9>"$RESULTS_DIR/.run.lock"
  if ! flock -n 9; then
    echo "refused: another run holds $RESULTS_DIR/.run.lock; wait for it or stop it first" >&2
    exit 2
  fi
fi

log="$RESULTS_DIR/bench-$industry.log"
results="$RESULTS_DIR/bench-$industry.jsonl"
attempt_out="$(mktemp)"
trap 'rm -f "$attempt_out"' EXIT
extra=()
if [ "$RETRY_ERRORS" = 1 ]; then
  extra=(--retry-errors)
fi

lines() { if [ -f "$results" ]; then wc -l < "$results"; else echo 0; fi; }

retries=0
before="$(lines)"
while :; do
  : > "$attempt_out"
  set +e
  "$AEBENCH" run "experiments/v2/benchmarks/$industry.json" --out "$RESULTS_DIR" \
    ${extra[@]+"${extra[@]}"} 2>&1 | tee -a "$log" "$attempt_out"
  rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" = 3 ] || break
  now="$(lines)"
  if [ "$now" -gt "$before" ]; then
    retries=0  # progress since the previous attempt: the budget starts again
  fi
  before="$now"
  if [ "$retries" -ge "$MAX_RETRIES" ]; then
    echo "stopped: $industry: model server gone, still after $MAX_RETRIES retries without progress; run again to resume" >&2
    exit 3
  fi
  retries=$((retries + 1))
  echo "stopped: $industry: model server gone (retry $retries of $MAX_RETRIES); retrying in ${RETRY_SLEEP}s" >&2
  sleep "$RETRY_SLEEP"
done

case "$rc" in
  0|1) ;;
  2) echo "$industry: refused (exit 2); see $log" >&2; exit 2 ;;
  *) echo "$industry: aebench exited $rc (unexpected); see $log" >&2; exit "$rc" ;;
esac

"$AEBENCH" report "$results" --out "$RESULTS_DIR/bench-$industry"

if [ "$rc" = 1 ]; then
  errors="$(sed -n 's/^rows=.* error=\([0-9][0-9]*\).*/\1/p' "$attempt_out" | tail -n 1)"
  echo "warning: $industry: ${errors:-some} error rows (status error); each counts as a failure in the report." \
    "Read their reason (the exception type) in $results, fix the cause, then run again with RETRY_ERRORS=1." >&2
  exit 1
fi
