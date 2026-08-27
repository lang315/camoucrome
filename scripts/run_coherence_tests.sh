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
PASS_COUNT=0
FAIL_COUNT=0

# $1: the CoherenceValidatorTest case name (must be a member of ORDER).
# Exit code of the gtest invocation is read via $? on the very next line, so
# nothing may run between that invocation and the call to this function.
report() {
  local name="$1" code="$2"
  if [ "$code" -eq 0 ]; then
    STATUS[$name]=PASS
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    STATUS[$name]=FAIL
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

env -u CAMOU_CONFIG -u CAMOUCFG_TEST_INVARIANT "$BINARY" \
  --gtest_filter='CoherenceValidatorTest.RegistryMatchesGeneratedHeader' \
  >/dev/null 2>&1
report RegistryMatchesGeneratedHeader $?

env -u CAMOU_CONFIG -u CAMOUCFG_TEST_INVARIANT "$BINARY" \
  --gtest_filter='CoherenceValidatorTest.EveryInvariantKeyIsDeclaredInTheRegistry' \
  >/dev/null 2>&1
report EveryInvariantKeyIsDeclaredInTheRegistry $?

env -u CAMOU_CONFIG -u CAMOUCFG_TEST_INVARIANT "$BINARY" \
  --gtest_filter='CoherenceValidatorTest.EveryInvariantIdIsUnique' \
  >/dev/null 2>&1
report EveryInvariantIdIsUnique $?

env -u CAMOU_CONFIG -u CAMOUCFG_TEST_INVARIANT "$BINARY" \
  --gtest_filter='CoherenceValidatorTest.MutationsExistForEveryInvariant' \
  >/dev/null 2>&1
report MutationsExistForEveryInvariant $?

CAMOU_CONFIG="$COHERENT" env -u CAMOUCFG_TEST_INVARIANT "$BINARY" \
  --gtest_filter='CoherenceValidatorTest.CleanConfigProducesNoViolations' \
  >/dev/null 2>&1
report CleanConfigProducesNoViolations $?

CAMOUCFG_TEST_INVARIANT=ua-os-family-agrees CAMOU_CONFIG="$INCOHERENT" \
  "$BINARY" \
  --gtest_filter='CoherenceValidatorTest.MutationIsCaughtAndNothingElseIs' \
  >/dev/null 2>&1
report MutationIsCaughtAndNothingElseIs $?

for name in "${ORDER[@]}"; do
  echo "${STATUS[$name]}  $name"
done

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "$PASS_COUNT/$TOTAL PASS"

if [ "$TOTAL" -ne 6 ]; then
  echo "error: expected 6 cases, ran $TOTAL" >&2
  exit 1
fi
if [ "$FAIL_COUNT" -ne 0 ]; then
  exit 1
fi
exit 0
