#!/bin/bash
# Drives every CoherenceValidatorTest case, each in its own process with
# exactly the environment it needs.
#
# camoucfg::Config() reads the environment once and caches it in a
# function-local static (mask_config.cc:18), so several differently
# configured cases cannot share one process -- whichever CAMOU_CONFIG that
# process happened to see first is the only one any case in it will ever
# see. That is why `--gtest_filter='CoherenceValidatorTest.*'` in a single
# invocation ALWAYS fails at least one case: MutationIsCaughtAndNothingElseIs
# needs an incoherent CAMOU_CONFIG and CleanConfigProducesNoViolations needs
# a coherent one, and one process can only latch one of the two.
#
# Covers all six CoherenceValidatorTest cases -- including
# EveryInvariantKeyIsDeclaredInTheRegistry, which the plan's own hand-typed
# runner in Task 4 Step 2 omitted. Asserts the count as well as each case's
# result: a runner that silently ran fewer than six cases and still exited 0
# would be exactly the failure mode this project keeps finding.
#
# Two guards keep that assertion honest instead of tautological -- both were
# missing in an earlier version of this script, which counted only how many
# times ITS OWN report() calls ran, i.e. how many `--gtest_filter=...` lines
# this file contains. A typo'd filter that matches nothing still exits 0 and
# gets counted as a pass under that scheme.
#
#   (a) Per case, the gtest binary's own summary line decides PASS/FAIL, not
#       merely its exit code. A filter matching zero tests also exits 0, so
#       `report "$name" "$?"` alone cannot tell "ran and passed" from
#       "matched nothing" -- see run_case() below.
#   (b) The expected case count is asked of the BINARY via --gtest_list_tests,
#       not hardcoded as `-ne 6`. A CoherenceValidatorTest case added to the
#       .cc and never added to ORDER is otherwise never run and nothing says
#       so -- the same shape as keys_unittest.cc's
#       EveryUaKeyExceptOsInfoIsInTheMetadataGroup, one file over.
#
# Usage: scripts/run_coherence_tests.sh [path-to-components_unittests]
set -uo pipefail

BINARY="${1:-$HOME/chromium/src/out/Default/components_unittests}"
if [ ! -x "$BINARY" ]; then
  echo "error: '$BINARY' is not an executable file" >&2
  exit 1
fi

COHERENT='{"ua:osInfo":"Windows NT 10.0; Win64; x64","ua:platform":"Windows"}'
INCOHERENT='{"ua:osInfo":"Windows NT 10.0; Win64; x64","ua:platform":"Linux"}'

declare -a ORDER=(
  RegistryMatchesGeneratedHeader
  EveryInvariantKeyIsDeclaredInTheRegistry
  EveryInvariantIdIsUnique
  MutationsExistForEveryInvariant
  CleanConfigProducesNoViolations
  MutationIsCaughtAndNothingElseIs
)
declare -A STATUS
# Seeded with a sentinel for every ORDER entry before any run_case call, so
# that a call site whose name argument does not match ORDER exactly -- a
# typo, or a run_case call deleted outright -- shows up as that entry never
# leaving MISSING, instead of the final print loop dying on
# "STATUS[$name]: unbound variable" under `set -u`. Found by mutation-testing
# this script: the crash still exits nonzero, so nothing was silently
# reported as passing, but the bash internal error obscured which case was
# actually missing.
for name in "${ORDER[@]}"; do
  STATUS[$name]=MISSING
done
PASS_COUNT=0
FAIL_COUNT=0

# (b) Ask the binary how many CoherenceValidatorTest cases it actually has,
# rather than trusting that ORDER above still lists them all. --gtest_list_tests
# with the suite filter prints one header line ("CoherenceValidatorTest.")
# followed by one two-space-indented line per case; count those.
LISTING=$(env -u CAMOU_CONFIG -u CAMOUCFG_TEST_INVARIANT "$BINARY" \
  --gtest_filter='CoherenceValidatorTest.*' --gtest_list_tests 2>&1)
LISTED_COUNT=$(grep -c '^  [A-Za-z]' <<<"$LISTING")
if [ "$LISTED_COUNT" -ne "${#ORDER[@]}" ]; then
  echo "error: binary reports $LISTED_COUNT CoherenceValidatorTest case(s)," \
       "this script's ORDER lists ${#ORDER[@]}. A case was added to the .cc" \
       "and not to ORDER (or vice versa)." >&2
  echo "$LISTING" >&2
  exit 1
fi

# (a) Runs one CoherenceValidatorTest case and records PASS only when gtest's
# own summary line confirms exactly one test ran and passed -- an exit code
# of 0 alone does not distinguish that from a filter matching zero tests.
# "$@" is the environment-wrapped invocation up to and including the binary;
# this function appends --gtest_filter.
#
# `out=$(...); code=$?` reads the exit status on the very next statement, so
# nothing may run between the invocation and reading $? -- the same
# constraint report() in the previous version of this script documented.
run_case() {
  local name="$1"
  shift
  local out code
  out=$("$@" --gtest_filter="CoherenceValidatorTest.$name" 2>&1)
  code=$?
  if [ "$code" -eq 0 ] && grep -qE '^\[  PASSED  \] 1 test\.$' <<<"$out"; then
    STATUS[$name]=PASS
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    STATUS[$name]=FAIL
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo "--- $name: exit=$code, no '[  PASSED  ] 1 test.' in output ---" >&2
    echo "$out" >&2
  fi
}

run_case RegistryMatchesGeneratedHeader \
  env -u CAMOU_CONFIG -u CAMOUCFG_TEST_INVARIANT "$BINARY"

run_case EveryInvariantKeyIsDeclaredInTheRegistry \
  env -u CAMOU_CONFIG -u CAMOUCFG_TEST_INVARIANT "$BINARY"

run_case EveryInvariantIdIsUnique \
  env -u CAMOU_CONFIG -u CAMOUCFG_TEST_INVARIANT "$BINARY"

run_case MutationsExistForEveryInvariant \
  env -u CAMOU_CONFIG -u CAMOUCFG_TEST_INVARIANT "$BINARY"

run_case CleanConfigProducesNoViolations \
  env -u CAMOUCFG_TEST_INVARIANT CAMOU_CONFIG="$COHERENT" "$BINARY"

run_case MutationIsCaughtAndNothingElseIs \
  env CAMOUCFG_TEST_INVARIANT=ua-os-family-agrees CAMOU_CONFIG="$INCOHERENT" "$BINARY"

for name in "${ORDER[@]}"; do
  if [ "${STATUS[$name]}" = MISSING ]; then
    echo "error: no run_case call ran for '$name' -- ORDER lists it but" \
         "nothing invoked it (a typo in the run_case argument, or the call" \
         "was deleted)." >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  echo "${STATUS[$name]}  $name"
done

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "$PASS_COUNT/$TOTAL PASS"

if [ "$FAIL_COUNT" -ne 0 ]; then
  exit 1
fi
exit 0
