#!/bin/sh
# Run the remaining failover scenarios sequentially. Each run_test.py invocation
# restores the baseline before and after, so a failure in one does not block the
# next. Progress and per-scenario "events:" lines land in results/batch.log.
cd "$(dirname "$0")/.." || exit 1
export TREX_EXT_LIBS="$PWD/vendor/trex-ext-libs"
PYT=".venv-trex/bin/python"
run() { echo "===== BEGIN $* @ $(date +%H:%M:%S)"; $PYT tests/run_test.py "$@" 2>&1 | grep -E 'switch active|state change|link [0-9]+ (stop|start)|node .* (stop|start)|remove|asp drop deltas|iperf3:|events:|saved|WARNING|Traceback|Error' ; echo "===== END $* @ $(date +%H:%M:%S)"; }
run T3 --pair A --then-failover --settle 30 --hold 150 --cps 30 --flow-hold 120
run T4 --pair A --settle 30 --hold 120 --cps 30 --flow-hold 90
run T5 --settle 30 --hold 120 --cps 30 --flow-hold 90
run T6 --settle 30 --hold 150 --cps 30 --flow-hold 120
run T9 --settle 30 --hold 150 --cps 30 --flow-hold 120
run T8 --loss 1 --settle 30 --hold 100 --cps 30 --flow-hold 90
run T8 --loss 5 --settle 30 --hold 100 --cps 30 --flow-hold 90
for lat in 0 2 4 11 18; do run T7 --pair A --latency $lat --settle 25 --hold 90 --cps 30 --flow-hold 70; done
echo "===== ALL DONE @ $(date +%H:%M:%S)"
