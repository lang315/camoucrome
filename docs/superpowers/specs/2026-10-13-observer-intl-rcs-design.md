# Tracking observer phase 2: Intl counts from V8 runtime call stats — design

Approved in brainstorming on 2026-10-12/13 (follow-up D). Extends
`docs/superpowers/specs/2026-10-06-tracking-observer-design.md`, whose "Not
observable" list starts with the V8 built-ins this slice makes visible.

## Goal

The observer report says, per site, how many times a page called the Intl
built-ins a fingerprinting script uses to read the time zone and locales
(`Intl.DateTimeFormat`, `resolvedOptions`, the `supportedLocalesOf` family,
`toLocale*`), next to the Blink surfaces it already counts.

## Approach: V8's runtime call stats, no V8 patch

`followups.md` assumed phase 2 needs a trace event inside
`v8/src/builtins/builtins-intl.cc`, so a patch in the separate `v8/` repo and
second-repo support in `apply.sh`, `export.sh`, `check_checkout_sync.sh`,
`rebuild_branch.sh` and `repin.py`. That is not needed. V8 already counts every
C++ builtin call and writes the counts into the trace when runtime call stats
(RCS) are compiled in and their category is on:

- `BUILTIN(Name)` (`v8/src/builtins/builtins-utils.h:135-148`) wraps every C++
  builtin in `RCS_SCOPE(isolate, RuntimeCallCounterId::kBuiltin_Name)` when
  stats are enabled. All the Intl entry points above are C++ builtins in
  `builtins-intl.cc` (`DateTimeFormatConstructor`,
  `DateTimeFormatPrototypeResolvedOptions`, `DateTimeFormatSupportedLocalesOf`,
  the `*ResolvedOptions`/`*SupportedLocalesOf` pairs of the other Intl
  constructors, `IntlGetCanonicalLocales`, `IntlSupportedValuesOf`).
- The counters are compiled in only with GN arg
  `v8_enable_runtime_call_stats = true` (default `false` on this pin,
  `v8/gni/v8.gni:194`). It adds the define `V8_RUNTIME_CALL_STATS` in a V8
  internal config (`v8/BUILD.gn:1857`). Nothing in `v8/include` or Blink reads
  it, so the arg rebuilds V8, the snapshot and the links, not Blink.
- At runtime the counters switch on with the trace category
  `disabled-by-default-v8.runtime_stats`
  (`v8/src/tracing/tracing-category-observer.cc:46-58`).
- This build uses Perfetto (`v8_use_perfetto = true`). Each top-level V8 entry
  slice, `TRACE_EVENT_CALL_STATS_SCOPED(isolate, "v8", "V8.Execute")` in
  `api.cc` and `V8.RunMicrotasks` in `microtask-queue.cc`, resets the table at
  its BEGIN and attaches a `runtime-call-stats` dump at its END
  (`v8/src/tracing/trace-event.h:633-660`). Nested scopes do neither
  (`has_parent_scope_ = table->InUse()`). So each dump holds the counts of one
  top-level slice, and the report sums dumps without double counting.
- A dedicated worker is its own isolate on its own thread. It enters V8
  through the same `api.cc` scopes, so its calls arrive in its own
  `V8.Execute` dumps. The `V8.RuntimeStats` instant in
  `runtime-call-stats.cc:349` is for V8's background compile and GC threads,
  not Web Workers, and the report ignores it.

Outcome: no `v8/` patch, no change to the change-set tooling, nothing for the
156 re-pin to carry. The change is one GN arg in the observer's out dirs, two
trace categories in the recording recipe, and report, verify and docs changes
in this repo.

`Date.prototype.getTimezoneOffset` is a CSA builtin (`TFJ`), not a C++
`BUILTIN`, so RCS does not count it, and it stays blind. The same goes for
`Math`.

## Components

### Build

- Observer out dirs add `v8_enable_runtime_call_stats = true` next to
  `camou_observe = true`: the box's `out/Default` (CI's), then the Windows
  `out\Observe`. `docs/observer/README.md` lists both args. `settings/` stays
  release-parity only.
- Landing order. `out/Default/args.gn` is box-local, so the sync gate does not
  see it. Once `verify_observe.py` asserts the Intl rows, a merge before the
  box rebuild turns CI red on those rows. So do it in this order:
  1. Edit `args.gn` under lock `observe-D`, messaging canvas before and after.
  2. Rebuild `chrome content_shell components_unittests` and record the
     non-zero step count and the wall time.
  3. Run the verify by hand.
  4. Merge.
- Windows `out\Observe` is a long native build. It is rebuilt only after
  canvas agrees, under the same lock, and after the box build is GREEN.

### Recording (opt-in)

`v8` is a default category with many events, and RCS times every builtin and
runtime call. So the default recipe stays as it is. The Intl recipe adds two
categories:

    --trace-startup=-*,disabled-by-default-camou.observe,v8,disabled-by-default-v8.runtime_stats

- `docs/observer/README.md` gives it as a second recipe. The first recording
  measures two numbers against the default recipe on the verify probe: trace
  size, and `verify_observe.py --timing`. Both go in the README.
- `scripts/windows/observe-recon.ps1` gets a `-Intl` switch that adds the two
  categories. Its default argv is unchanged, so arm runs stay comparable with
  2026-10-07.

### Report (`scripts/observe_report.py`)

A new section, "V8 built-ins (Intl)", comes after the per-site tables.

- Input: every event whose name is `V8.Execute` or `V8.RunMicrotasks` and that
  carries a `runtime-call-stats` dump. The JSON exporter places an END-event
  annotation somewhere that this repo has not observed yet: in the `X`
  event's `args`, or on a separate `E` event. The parser matches the shape of
  the first trace recorded on the rebuilt box build, and the unit fixture
  copies that event verbatim. The verify's count == K rows catch a parser that
  reads the wrong place.
- Counted names: a dump is a dict of `name -> [count, time]`. Rows are per
  counter name, not a family sum, for names matching
  `^Builtin_(Intl|DateTimeFormat|NumberFormat|Collator|PluralRules|RelativeTimeFormat|ListFormat|DisplayNames|Segmenter|DurationFormat|Locale|V8BreakIterator)`
  or `^Builtin_\w+PrototypeToLocale`. The section prints only counters that
  occurred, sorted by count.
- Site: the slice's `pid`, mapped to the site of the `camou.observe` events
  from the same pid, which is one renderer per site under site isolation. If
  the pid has no observer event, the site is `(site unknown)`.
- Script, in order:
  1. The slice lies inside a Blink `v8.run` slice on the same pid/tid
     (`v8_script_runner.cc:478`, arg `fileName`). The script is that file,
     shortened with `script_label`.
  2. Otherwise, every `camou.observe` event inside the slice carries one and
     the same `script`. The script is that one.
  3. Otherwise, `(unknown)`.

  Only `v8.run` has a file name. `v8.callFunction` (819),
  `v8.callAsConstructor` (767) and `v8.evaluateModule` (936) have none. So
  event handlers, timers, promise callbacks and module bodies, which is where
  third-party SDKs such as `fbevents.js` mostly run, get a script only
  through rule 2. The report states this limit under the section.
- Blind rule. The section prints `Intl: blind (no V8 runtime call stats in
  this trace)` when no dump in the trace holds any counter. The rule is "no
  counter", not "no dump", for two reasons:
  - With `v8` on and `runtime_stats` off, the `V8.Execute` END lambda still
    runs and can attach an empty dump.
  - With counting on, any script execution produces `Builtin_*` or `Runtime_*`
    counters, so an all-empty trace means counting was off.

  A trace with counters but no Intl call prints `Intl: none called`. Those are
  the only two zero states.
- `NOT_OBSERVABLE` loses the Intl clause. It keeps
  `Date.prototype.getTimezoneOffset` (CSA) and `Math`, plus a line saying Intl
  counts need the Intl recipe and an RCS build.

### Verify (`scripts/verify_observe.py`, RED-first)

- The probe page and the worker each run:
  - `new Intl.DateTimeFormat()` K times, keeping the objects;
  - `resolvedOptions()` once on each of those objects;
  - `Intl.DateTimeFormat.supportedLocalesOf(['en'])` K times.
- The on arm records with the Intl recipe. It asserts these three counters,
  each exactly K on the main thread (script = probe page) and on the worker
  (script = `/worker.js`):
  - `Builtin_DateTimeFormatConstructor`
  - `Builtin_DateTimeFormatPrototypeResolvedOptions`
  - `Builtin_DateTimeFormatSupportedLocalesOf`

  The existing camou.observe rows stay as they are.
- `--red` expects K+1 on these rows as well, and must FAIL.
- Blind check, in two arms:
  - The existing off arm (`blink,loading`) must make the report print the
    blind line.
  - A new arm records `-*,disabled-by-default-camou.observe,v8`, so `v8` is on
    and `runtime_stats` is off. Its report must print the blind line too. This
    is the RED check for the blind rule.
- `scripts/test_observe_report.py` adds fixture tests:
  - sum across two dumps;
  - the regex keeps Intl names and drops others;
  - script attribution through `v8.run`, through the single-script rule, and
    `(unknown)`;
  - blind for an empty dump;
  - `none called`.

  `scripts/test_verify_observe.py` covers the new rows.

### Docs

- `docs/observer/followups.md`: the phase 2 item points to this spec and drops
  the second-repo claim. When the slice lands, it moves out of the open
  list.
- When the slice lands, `docs/observer/README.md` and the phase-1 spec's "Not
  observable" bullet are updated.

## Non-goals

- No V8 patch, and no second-repo tooling.
- No `getTimezoneOffset`, and no `Math`.
- No values: the report counts calls, as for Blink surfaces.
- No exact caller per call. Attribution is the entry slice.
- No change to the default recording recipe.

## Risks

- **Build cost unmeasured.** The arg recompiles V8. Estimate 30-90 min on the
  box. The step count is recorded.
- **Overhead with RCS on.** RCS timing slows builtins. A page that times
  itself could act differently under the Intl recipe. The recipe is opt-in,
  and the `--timing` delta is published.
- **JSON shape of the END annotation** is unconfirmed until the first
  recording. It is fixed from that trace, and the count == K rows guard it.
- **CI coupling.** CI's verify needs the box arg. The landing order above
  covers it. A box `args.gn` reset (for example at the 156 re-pin) must keep
  the arg. The re-pin runbook's out-dir step gets one line.
