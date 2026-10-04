# Step 2: measurement, layers 1 and 2 — design

Roadmap: `plans/2026-10-02-long-term-roadmap.md`, "Step 2". Approved in
brainstorming on 2026-10-04: one spec, built in phases; the network row measured
through an external echo service; detector results reduced by a generic text
diff plus two small parsers.

## Goal

Know what detectors see, for the fork and for a stock control, before choosing
any new spoofing work. The output is a set of tables, one per probe, listing
every row where the fork differs from the control. The tables, not the backlog
list, re-rank the backlog.

## What exists, and why it is not enough

- `verify_host_oracle.py` (layer 1) runs the fork through the Python client
  (`camoucrome.probe`) with `--use-gl=angle --use-angle=swiftshader`. The stock
  side is `baselines/chrome-8037-stock-oracle-windows.json`, captured by
  `capture_host_oracle.py` through `winhost.py` with `Start-Process` and
  `--use-angle=d3d11`. The two arms use different launchers and different
  argv, which is what the roadmap's precondition forbids.
- The verify compares the fork's **headless** run against the baseline's
  **headed** column (`verify_host_oracle.py:28`). Headless tells then read as
  fork differences, or hide them.
- SwiftShader makes the fork's WebGPU adapter null, so the oracle drops the
  whole `gpu` subtree (backlog item 2).
- Nothing exists for public detectors, relaunch stability, cross-profile
  linkability, noise readback or the network fingerprint. `echo_server.py`
  stores headers in a dict (order lost) and speaks plain HTTP/1.1 only.

What can be reused: `camoucrome.launch(playwright, executable_path, config=None,
...)` launches any Chrome, stock included; `windows_verify_set.py` already swaps
`CAMOU_EXE` between stock and fork; `capture_host_oracle.page()` is the oracle
page; `profile_seeds(user_data_dir)` persists per-profile seeds.

## Architecture

One runner, `scripts/measure_step2.py`, run natively on the Windows host in the
client venv (Python 3.12, patchright 1.62.3). No Chromium build is needed.

### Arms

| Arm | Executable | Config |
|---|---|---|
| control | `C:\Program Files\Google\Chrome\Application\chrome.exe` (stock, held at the pin by disabling Google Update) | none (`config=None`) |
| fork | `D:\camou-win\chromium\src\out\Release\chrome.exe` | a generated Windows identity from a fixed seed, with `profile_seeds` |

Both arms go through the same `camoucrome.launch()` call. Only the executable
and the config differ.

### Preconditions, asserted at start

- Both executables report the pin's version (`upstream.env`, today
  `154.0.8037.93`). A mismatch stops the run before anything is measured.
- **Argv parity.** The runner records the browser argv of both arms (from
  `launch()`'s built args) and stops unless the difference is inside a named
  allow-list. Today the list holds `--accept-lang=…`, which the client derives
  from the identity. Neither arm gets `--use-angle=swiftshader` or
  `--no-sandbox`; both run under the real sandbox and the host GPU.

### Columns

Every probe runs for each arm in two modes, `headed` and `headless`, giving four
cells per probe. The headed launches run inside the SSH session, so the window
is on a desktop nobody sees (`winhost.py` records the same). Screen rows from
that column describe that desktop, and the tables say so.

### Probes

Each probe is a function `(arm, mode) -> {row_name: value}`. The comparison
labels every row that differs between fork and control as one of:

- `expected`: the identity puts it there, and the label names the key or reason;
- `volatile`: it changes between runs of the same arm, from a named list;
- `unexpected`: everything else. Only these are findings.

1. **L1 oracle.** The `capture_host_oracle.page()` page, loaded in both arms.
   The comparison rules (`KNOWN`, `KNOWN_PREFIX`, `SHAPE_ONLY`) move out of
   `verify_host_oracle.py` into a module both scripts import. With no
   SwiftShader the `gpu` subtree is compared again. A direct `launch()` adds no
   `__camou_init` marker, so the `windowKeys`/`windowNames`/`protoCounts.Window`
   exclusions may become unnecessary. If they do, rule 2 (window keys equal to
   stock) is measured on `chrome.exe`, and the measurement doc records that.
2. **L2 public detectors.** CreepJS, BrowserScan, Pixelscan and sannysoft. Each
   page is read until two consecutive reads of its text are identical, or until
   a timeout. A timeout scores the detector `UNMEASURED`, never a difference.
   The runner stores the raw `innerText` and a screenshot (both local only),
   then diffs fork against control line by line. sannysoft's result table and
   CreepJS's structured sections get small parsers that yield key/value rows.
   For the other two, the line diff is the result. No aggregate score.
3. **Stability across relaunch.** Each arm launches one profile twice and runs
   the oracle page both times. Every leaf must match across the two launches:
   canvas and audio hashes and media device IDs above all.
4. **Cross-profile linkability.** Two fork profiles from seeds 1 and 2 run the
   oracle page. The table lists the leaves the two share. The control is two
   stock profiles, which share everything. This probe records only and scores
   nothing. The known shared 119-family font list belongs in it.
5. **Noise readback.** A canvas 2D solid fill read back with `getImageData`,
   and a WebGL clear read back with `readPixels`. Each row is the number of
   distinct colours read. The control reads 1. A fork reading more than 1 is
   a farbling tell.
6. **Network.** The page loads `https://tls.peet.ws/api/all`, and the runner
   keeps `ja4`, `http2.akamai_fingerprint`, and the pseudo-header and header
   order. `ja3` is volatile (Chrome permutes its extension order). Header values
   the identity sets (User-Agent, Accept-Language) are `expected`. The fork
   should inherit all of this unchanged; this row proves it. The request goes
   to a third party; this was accepted, and layer 2 hits public sites anyway.

### Output

- Raw JSON for every cell, plus screenshots and raw detector text, goes to a
  run directory under the temp dir.
- `tables.md`: per probe and per column, every differing row with its label.
- `measure_step2.py --compare RUN_A RUN_B` matches two runs row by row and
  lists every disagreement outside the named volatile list.
- The committed baseline is the row JSON plus `tables.md` under
  `docs/superpowers/measurements/`, never screenshots or raw detector text.

## Testing

### Unit tests (offline, pytest, picked up by `checks.yml`)

Pure functions, each test seen failing first:

- the row diff and its labelling;
- the sannysoft and CreepJS parsers, on saved text fixtures;
- the argv allow-list check;
- the version precondition;
- `--compare`.

### RED-first on the host

Each probe must show it can see a difference before its "no difference" counts.

| Probe | Null run (control against control) | Planted difference |
|---|---|---|
| L1 oracle | 0 `unexpected` rows: the noise floor | A flag on one arm that removes an API, for example `--disable-features=WebShare`; that leaf must appear |
| L2 detectors | Only `volatile` lines; this run calibrates the volatile list | The same flag changes at least one detector line |
| Relaunch | The control is stable | The fork launched without `profile_seeds` (fresh seeds per launch); the canvas hash must change |
| Linkability | The control shares every leaf (presence) | none |
| Noise | The control reads 1 colour | A two-colour fill reads 2 |
| Network | `ja4` is equal | `--ssl-version-max=tls1.2` on one arm changes `ja4` |

The plan fixes each planted flag after grepping the 154 tree to confirm it
exists and does what the row needs.

## Operation

- The runner holds the build lock (`scripts/build_lock.sh`, owner `step2`) for
  the whole run, so no WSL or Windows build loads the machine meanwhile.
  Machine load has already moved a timing row once (the C5 flake, 2026-10-03).
  The lock is taken and released as a procedure step, around the run.
- **Schedule.** The baseline at 154 must be committed before the re-pin due
  2026-10-20. Google Update on the host stays disabled until then. At the
  re-pin the baseline is recaptured on 156 (runbook §7).

## Done when

- One command produces every table for both arms, headed and headless.
- Two runs agree under `--compare`, apart from the named volatile list.
- The 154 baseline and the RED evidence are committed under
  `docs/superpowers/measurements/`.
- The roadmap marks step 2 done and re-ranks the backlog from the tables.

## Out of scope

- Layer 3 (commercial anti-bot): backlog item 1.
- Fixing anything the tables find. Each finding becomes a backlog entry.
- A local TLS server. The external echo service was chosen; a local one is the
  fallback if the service disappears.
