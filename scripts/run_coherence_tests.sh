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

# Clear every CAMOU_CONFIG* variable, not just the bare name. The transport
# gives NUMBERED chunks precedence -- AssembleRawConfig() returns the
# concatenated chunks whenever they are non-empty and only FALLS BACK to the
# unnumbered variable -- so a leftover CAMOU_CONFIG_1 in the operator's shell
# outranks everything the run_case lines below set. This machine is exactly
# where such leftovers are made. lib_shell.py has done this from the start;
# this runner is the one artifact that did not inherit the hardening.
#
# It fails closed today rather than green: a stale chunk almost never carries
# both ua:osInfo and ua:platform, so CleanConfigProducesNoViolations' asserts
# catch it, and one that carried both incoherently turns
# MutationIsCaughtAndNothingElseIs red. Closed anyway -- "fails closed" is a
# property of today's test set, not of the mechanism.
while IFS='=' read -r var _; do
  case "$var" in CAMOU_CONFIG*|CAMOU_PRESET*) unset "$var" ;; esac
done < <(env)

# Coherent across every relation: a Windows UA with a Windows platform, and a
# screen cluster with availWidth == width and availHeight == height (the real
# no-taskbar state the fits-within relation must accept). The screen keys are
# what makes CleanConfigProducesNoViolations exercise the equality boundary; a
# `<` typo in CheckFitsWithin would turn this config incoherent and fail here.
# SP5b pairs are all present and coherent (Windows OS with a Direct3D11
# renderer on both context types, one locale on all three language keys), so
# CleanConfigProducesNoViolations exercises every relation.
COHERENT='{"ua:osInfo":"Windows NT 10.0; Win64; x64","ua:platform":"Windows","screen.width":1920,"screen.height":1080,"screen.availWidth":1920,"screen.availHeight":1080,"navigator.platform":"Win32","locale:tag":"en-US","navigator.language":"en-US","navigator.languages":["en-US","en"],"timezone:id":"America/New_York","mediaDevices:enabled":true,"mediaDevices:seed":7,"webGl:vendor":"Google Inc. (NVIDIA)","webGl:renderer":"ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)","webGl2:vendor":"Google Inc. (NVIDIA)","webGl2:renderer":"ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"}'
INCOHERENT='{"ua:osInfo":"Windows NT 10.0; Win64; x64","ua:platform":"Linux"}'

# One incoherent config per registry invariant, each violating exactly that
# invariant. MutationIsCaughtAndNothingElseIs is run once per entry, in its own
# process (the config latches per process). Keyed by invariant id; must mirror
# coherence_validator_unittest.cc's kMutations and settings/invariants.json.
# The drift guard below asserts this map covers every invariant in the registry
# -- a mutation defined in kMutations but never driven here is "documentation,
# not enforcement", the exact failure MutationIsCaughtAndNothingElseIs exists
# to prevent, silently un-run.
declare -A MUTATIONS=(
  [ua-os-family-agrees]="$INCOHERENT"
  [screen-avail-width-fits]='{"screen.width":1920,"screen.availWidth":2560}'
  [screen-avail-height-fits]='{"screen.height":1080,"screen.availHeight":1440}'
  [navigator-platform-matches-os]='{"ua:osInfo":"Windows NT 10.0; Win64; x64","navigator.platform":"MacIntel"}'
  [navigator-language-heads-languages]='{"navigator.languages":["fr-FR","en-US"],"navigator.language":"en-US"}'
  [locale-tag-matches-navigator-language]='{"locale:tag":"fr-FR","navigator.language":"en-US","timezone:id":"Europe/Paris"}'
  [webgl2-vendor-agrees-with-webgl]='{"webGl:vendor":"Google Inc. (NVIDIA)","webGl:renderer":"ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)","webGl2:vendor":"Google Inc. (AMD)","webGl2:renderer":"ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"}'
  [webgl2-renderer-agrees-with-webgl]='{"webGl:vendor":"Google Inc. (NVIDIA)","webGl:parameters":{"37446":"ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"},"webGl2:vendor":"Google Inc. (NVIDIA)","webGl2:renderer":"ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 (0x00002684) Direct3D11 vs_5_0 ps_5_0, D3D11)"}'
  [webgl-renderer-backend-fits-os]='{"ua:osInfo":"Windows NT 10.0; Win64; x64","webGl:vendor":"Google Inc. (Apple)","webGl:renderer":"ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)","webGl2:vendor":"Google Inc. (Apple)","webGl2:renderer":"ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)"}'
  [timezone-set-with-locale]='{"locale:tag":"fr-FR"}'
  [mediadevices-seed-when-enabled]='{"mediaDevices:enabled":true}'
  [webgl-identity-set-on-both-contexts]='{"webGl:vendor":"Google Inc. (NVIDIA)","webGl:renderer":"ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"}'
)

declare -a ORDER=(
  RegistryMatchesGeneratedHeader
  EveryInvariantKeyIsDeclaredInTheRegistry
  EveryInvariantIdIsUnique
  MutationsExistForEveryInvariant
  CleanConfigProducesNoViolations
  MutationIsCaughtAndNothingElseIs
  ShippedPresetProducesNoViolations
)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
# Counted from ORDER in the summary loop, NOT incremented in run_case. A
# typo'd run_case argument writes STATUS under a key ORDER does not contain, so
# incrementing in both places counted that invocation and the MISSING entry it
# left behind -- a real failure, reported as "5/7 PASS" for six cases.

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

# Drift guard for MUTATIONS, in the same spirit as (b): derive the expected
# count from the source of truth rather than hardcode it. invariants.json sits
# at <src>/components/camoucfg/invariants.json, and the binary lives under
# <src>/out/..., so strip at /out/ to find the src root. Each invariant is one
# `"id":` line; the $comment block's strings never start with that key.
JSON="${BINARY%/out/*}/components/camoucfg/invariants.json"
if [ ! -f "$JSON" ]; then
  echo "error: cannot find invariants.json at '$JSON' (derived from the" \
       "binary path) to check that every registry invariant has a mutation" \
       "driven here." >&2
  exit 1
fi
REGISTRY_COUNT=$(grep -cE '^[[:space:]]*"id"[[:space:]]*:' "$JSON")
if [ "$REGISTRY_COUNT" -eq 0 ]; then
  echo "error: found no invariant ids in '$JSON' -- the grep pattern has" \
       "drifted from the file's shape, or the file is empty. Zero would make" \
       "the mutation loop below run zero times and pass vacuously." >&2
  exit 1
fi
if [ "$REGISTRY_COUNT" -ne "${#MUTATIONS[@]}" ]; then
  echo "error: invariants.json declares $REGISTRY_COUNT invariant(s), this" \
       "runner drives ${#MUTATIONS[@]} mutation(s). An invariant was added to" \
       "the registry without a mutation run here -- its" \
       "MutationIsCaughtAndNothingElseIs case would never execute." >&2
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
  # --test-launcher-print-test-stdio=always: the launcher runs the case in a
  # child process and swallows its stderr on success, so without it check (c)
  # below would count zero warnings on any binary. Measured: 0 on a binary
  # known to warn, before the flag was added.
  out=$("$@" --gtest_filter="CoherenceValidatorTest.$name" \
        --test-launcher-print-test-stdio=always 2>&1)
  code=$?
  LAST_OUT="$out"
  if [ "$code" -eq 0 ] && grep -qE '^\[  PASSED  \] 1 test\.$' <<<"$out"; then
    STATUS[$name]=PASS
  else
    STATUS[$name]=FAIL
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

# (c) The coherent config must also produce zero wrong-type warnings. A check
# that probes a key through a getter of another type (KeyIsSet did, before it
# read the raw value) logs "falling back to the real value" for a value that
# is in fact used -- a false warning on every startup, invisible to gtest.
WARN_COUNT=$(grep -c 'falling back to the real value' <<<"$LAST_OUT" || true)
if [ "$WARN_COUNT" -ne 0 ]; then
  echo "--- CleanConfigProducesNoViolations: $WARN_COUNT wrong-type warning(s)" \
       "on the coherent config ---" >&2
  grep 'falling back to the real value' <<<"$LAST_OUT" >&2
  STATUS[CleanConfigProducesNoViolations]=FAIL
fi

# MutationIsCaughtAndNothingElseIs is one gtest case driven once per registry
# mutation, each in its own process with the config that violates exactly that
# invariant. The single ORDER/STATUS slot for the case passes only if every
# per-mutation run passes -- a run_case per id would clobber the shared slot,
# recording only the last mutation's result.
mutation_all_pass=1
for id in "${!MUTATIONS[@]}"; do
  mout=$(env CAMOUCFG_TEST_INVARIANT="$id" CAMOU_CONFIG="${MUTATIONS[$id]}" \
    "$BINARY" \
    --gtest_filter="CoherenceValidatorTest.MutationIsCaughtAndNothingElseIs" \
    2>&1)
  mcode=$?
  if [ "$mcode" -eq 0 ] && grep -qE '^\[  PASSED  \] 1 test\.$' <<<"$mout"; then
    # One line per driven mutation, so the transcript records that every
    # registry entry was actually exercised -- the single ORDER slot below
    # cannot show how many ran.
    echo "PASS  MutationIsCaughtAndNothingElseIs[$id]"
    continue
  fi
  mutation_all_pass=0
  echo "--- MutationIsCaughtAndNothingElseIs[$id]: exit=$mcode, no" \
       "'[  PASSED  ] 1 test.' in output ---" >&2
  echo "$mout" >&2
done
if [ "$mutation_all_pass" -eq 1 ]; then
  STATUS[MutationIsCaughtAndNothingElseIs]=PASS
else
  STATUS[MutationIsCaughtAndNothingElseIs]=FAIL
fi

# ShippedPresetProducesNoViolations, one process per settings/presets/*.json
# with the file's content in CAMOU_PRESET and no CAMOU_CONFIG at all -- the
# preset path end to end, through the same ParsedConfig() hook the browser
# uses. One ORDER slot, same shape as the mutation loop above; zero preset
# files is a failure, not a vacuous pass.
preset_all_pass=1
preset_count=0
for preset in "$ROOT"/settings/presets/*.json; do
  [ -e "$preset" ] || continue
  preset_count=$((preset_count + 1))
  pout=$(env -u CAMOU_CONFIG -u CAMOUCFG_TEST_INVARIANT \
    CAMOU_PRESET="$(cat "$preset")" "$BINARY" \
    --gtest_filter="CoherenceValidatorTest.ShippedPresetProducesNoViolations" \
    --test-launcher-print-test-stdio=always 2>&1)
  pcode=$?
  pwarn=$(grep -c 'falling back to the real value' <<<"$pout" || true)
  if [ "$pcode" -eq 0 ] && [ "$pwarn" -eq 0 ] &&
     grep -qE '^\[  PASSED  \] 1 test\.$' <<<"$pout"; then
    echo "PASS  ShippedPresetProducesNoViolations[$(basename "$preset")]"
    continue
  fi
  preset_all_pass=0
  echo "--- ShippedPresetProducesNoViolations[$(basename "$preset")]:" \
       "exit=$pcode, wrong-type warnings=$pwarn ---" >&2
  echo "$pout" >&2
done
if [ "$preset_count" -eq 0 ]; then
  echo "error: no settings/presets/*.json under $ROOT" >&2
  preset_all_pass=0
fi
if [ "$preset_all_pass" -eq 1 ]; then
  STATUS[ShippedPresetProducesNoViolations]=PASS
else
  STATUS[ShippedPresetProducesNoViolations]=FAIL
fi

PASS_COUNT=0
FAIL_COUNT=0
for name in "${ORDER[@]}"; do
  if [ "${STATUS[$name]}" = MISSING ]; then
    echo "error: no run_case call ran for '$name' -- ORDER lists it but" \
         "nothing invoked it (a typo in the run_case argument, or the call" \
         "was deleted)." >&2
  fi
  if [ "${STATUS[$name]}" = PASS ]; then
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  echo "${STATUS[$name]}  $name"
done

echo "$PASS_COUNT/${#ORDER[@]} PASS"

if [ "$FAIL_COUNT" -ne 0 ]; then
  exit 1
fi
exit 0
