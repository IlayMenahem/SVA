# jasper-utils

Shared infrastructure for running JasperGold on remote hosts: upload inputs, run one
Jasper session per run directory, stop it cleanly, fetch outputs, tally CPU time, record
runs for `accelerate-sva-proofs`, and read traces. Use it instead of writing your own
runners, reporters and parsers.

It is design-agnostic: nothing here knows about a particular core, benchmark or check.

## Quickstart

Work from the directory that contains `jasper-utils/` (an agent's task directory).

```sh
export JGU_HOST=vlsi-77            # ssh host alias
export JGU_ROOT=my_ws/task         # remote workspace, relative to $HOME; created on demand
export JGU_TIMEOUT_S=1200          # session wall limit (elaboration + all proves)
export JGU_JOBS=2                  # engine job cap read by jgu::caps

jasper-utils/bin/jgu run --run counter-001 \
    --sync jasper-utils/examples/counter --tcl jasper-utils/examples/counter/run.tcl
```

This prints (actual output):

```
JGU_SUMMARY run=counter-final-001 exit=0 wall_s=3.5 time_cpu_s=0.7 sampled_cpu_s=0.1 effective_cpu_s=0.7 results=cex:1,covered:1,proven:3 results_json=ok
  le9: assert proven engine=Hp assumed=-
  never12: assert proven engine=PRE assumed=le9
  k_stable: assert proven engine=PRE assumed=jgu_rigid_k
  never5: assert cex engine=Ht assumed=-
  reach9: cover covered engine=Ht assumed=-
outputs: jgu-runs/counter-final-001
```

`examples/counter/run.tcl` shows every Tcl helper in one short script.

## Workflow

1. **Upload large shared inputs once.** `jgu push src` copies `src/` into `$JGU_ROOT/src`.
   Tcl scripts read it as `$::env(JGU_ROOT)/src/...`.
2. **Upload small, changing inputs with each run.** Each run uploads its `--sync` paths and
   its `--tcl` script into a fresh `$JGU_ROOT/runs/<run>/`, at the same relative paths.
3. **Run.** In the foreground, `jgu run` waits, fetches outputs into `jgu-runs/<run>/` and
   prints a summary. Ctrl-C or SIGTERM stops the remote run too. For long runs:
   ```sh
   jgu run --run disc-007 --detach ...     # returns at once
   jgu wait disc-007 --max 3000 --fetch    # exit 0 done, 3 still running, 1 lost
   jgu status disc-007 ; jgu list ; jgu kill disc-007
   ```
4. **Account.** `jgu cpu` totals the fetched runs (or every remote run with `--remote`). Add
   `--group '^([a-z]+)-'` to subtotal by run-name prefix. Report `effective_cpu_s`.
5. **Record a replay** for `accelerate-sva-proofs`:
   ```sh
   jgu record --name replay-001 --tool-version 'Cadence Jasper 2024.06p002' \
       --sync formal --tcl formal/replay.tcl --flist rtl/files.f --flist-relative
   ```
   - It writes the manifest to `proof-runs/manifests/replay-001.json`. The manifest holds the
     synced files, the Tcl script, the uploaded jgu support files, the `--flist` sources and
     any `--include` paths, plus the run's settings.
   - It then runs `jgu run` under `record_run.py`, with `jg.log`, `time.txt`, `exit_code`,
     `results.json` and `cpu_sample.txt` as reports.
   - The Tcl script must write `results.json` (`jgu::finish` does), otherwise the record has
     errors.
   - In the ledger, cite `reports/003-results.json`.

Run names are never reused: the remote `mkdir` fails when a name exists, and local output
directories must be new. Pick a fresh name, such as `-002`, for every run.

## Commands

| Command | Purpose |
|---|---|
| `run --run NAME --tcl F [--sync P]... [--detach]` | Upload, then start one session. Options: `--timeout`, `--jobs`, `--env K=V`, `--jg`, `--no-sample-cpu`, `--out`. |
| `record --name NAME ...` | `run` under `record_run.py` with a generated manifest. Options: `--tool-version`, `--manifest`, `--include`, `--flist`, `--setting`, `--skill`. |
| `push PATH...` | Upload shared inputs into `$JGU_ROOT`. |
| `status RUN`, `list` | One `JGU_STATUS` line per run, with `state` = new, running, done or lost. |
| `wait RUN [--poll S] [--max S] [--fetch]` | Poll until the run is no longer active. |
| `kill RUN` | Stop a run and keep its time record (see below). |
| `fetch RUN [--out DIR]` | Copy the outputs into a fresh local directory and summarize them. |
| `summary DIR...` | Summarize fetched runs. Exits 1 if a `results.json` is invalid. |
| `cpu [DIR...] [--remote] [--group RE]` | CPU table plus one `JGU_CPU_TOTAL {json}` line. |
| `manifest --out F ...` | Write a `record_run.py` manifest (`--include`, `--flist`, `--base`, `--setting`). |
| `flist F [-F] [--var K=V] [--json]` | Expand a `.f` file: `${VAR}`, `-f`/`-F` nesting, `+incdir+`, `+define+`, `-v`. |
| `vcd F --sig RE... [--clock RE] [--radix hex\|bin\|dec]` | Print a VCD as one row per clock cycle, numbered like Jasper (from 1). `--list` lists the signals. |

`--host` and `--root` default to `$JGU_HOST` and `$JGU_ROOT`. Setting `JGU_SSH_MUX=0`
disables ssh connection sharing.

## Tcl helpers (`tcl/jglib.tcl`)

Start every script with `source $::env(JGU_LIB)`. The script runs with the run directory as
its working directory, and these variables are set: `JGU_ROOT` (absolute), `JGU_RUN`,
`JGU_RUN_DIR`, `JGU_TCL`, `JGU_JOBS`, `JGU_LIB`, plus every `--env` value.

| Proc | Purpose |
|---|---|
| `jgu::script_dir` | Absolute directory of the running script. `info script` is empty under `jg -tcl`. |
| `jgu::caps ?jobs?` | `set_proofgrid_max_jobs` and the per-engine cap (default `$JGU_JOBS`). |
| `jgu::prove props engines limit_s` | `set_engine_mode`, `set_prove_time_limit`, `prove`. Returns the wall seconds. |
| `jgu::report tag props` | Print one `JGU_RESULT` line per property: id, kind, status, engine, time_s, depth. |
| `jgu::snapshot props` | Dict of statuses. Take it before adding any assume or stopat. |
| `jgu::props type ?glob?` | Properties of a type (`assert`, `assume`, `cover`). |
| `jgu::field prop name` | One `get_property_info` field, or `""`. |
| `jgu::dag_init` | `set_proven_directive false` and `set_prove_invariants_import off`. |
| `jgu::lemma id expr` | Declare an assert plus a disabled assume twin. Declare all lemmas before the first prove. |
| `jgu::prove_node prop deps engine limit_s ?id? ?premises?` | Enable the dependency twins, prove, record, then disable them. |
| `jgu::rigid sig ?cut?` | Hold a signal at one free value (`##1 $stable`). With `cut` = 1 it stops the signal first. |
| `jgu::precondition_covers props` | The automatic `<assert>:precondition*` covers. |
| `jgu::record ...`, `jgu::record_prop prop engine assumed ?id?` | Add a `results.json` entry. |
| `jgu::write_results ?path?`, `jgu::finish ?path?` | Write `results.json` in the skill's schema. `finish` then exits. |
| `jgu::trace_table prop signals ?path?` | Per-cycle table of a counterexample or cover trace. |
| `jgu::save_vcd prop path` | Save a trace as VCD (read it with `jgu vcd`). |

A DAG replay looks like this:

```tcl
jgu::dag_init
jgu::lemma l1 {...} ; jgu::lemma l2 {...}       ;# all declarations first
jgu::prove_node l1 {} Hp 900
jgu::prove_node l2 {l1} N 900
jgu::prove_node <embedded>::top.target {l1 l2} Hp 900 target
jgu::prove_node cov_pre {} Ht 300
jgu::finish
```

## Remote run directory and output formats

`$JGU_ROOT/runs/<run>/` contains:

- **The synced inputs**, at their local relative paths.
- **`.jgu/`**:
  - `jgu_run.sh`, `params.sh`, `jglib.tcl` and `cpu_sampler.py`;
  - `pgid` and `time.pid`;
  - `inputs.sha256`, a hash of every input taken before jg starts;
  - `started` and `finished` (epoch seconds), plus the markers `done` and `killed`.
- **`jg.log`**, Jasper's stdout and stderr.
- **`time.txt`**: GNU time output. When jg exits non-zero it also has a line like
  `Command exited with non-zero status N`, followed by
  `JGU_TIME wall= user= sys= maxrss_kb=`.
- **`exit_code`**: 0 means jg exited normally, 124 means the session hit `--timeout`, and 143
  means it was killed.
- **`cpu_sample.txt`**: `JGU_CPUSAMPLE total_cpu_s= procs= peak_procs= samples=`.
- **`results.json`**: written by the Tcl script.
- **`out/`**: free space for the Tcl script (traces, VCDs). `fetch` copies it.

Jasper runs as `/usr/bin/time timeout -k 30 T jg -batch -proj jgproj -tcl F`. `jgu kill`
signals `timeout`, which forwards TERM to the whole jg process group and waits, so `time` can
still write `time.txt`. If the run is still alive after the grace period, `kill` sends KILL to
both process groups. Never `pkill` by name: other agents share the hosts and the user.

## CPU accounting

`time.txt` is exact when jg exits by itself. It is far too low when jg is killed, whether by
`--timeout` or `jgu kill`, because the engine workers die before jg reaps them. In tests, a
run killed after 31 s recorded 0.09 s against 29.4 s sampled.

The sampler reads `/proc` every 5 s for every process in the session. That gives a lower
bound, and the bound survives kills. It is on by default; `--no-sample-cpu` turns it off.

`effective_cpu_s` is the larger of the two numbers for each run. Report it.

## Jasper pitfalls

- **New constraints clear proof results.** Adding an assume or stopat (including
  `assume -from_assert`) clears statuses. Declare everything first, and use `jgu::snapshot`
  before adding more.
- **Proven properties become hidden assumptions.** `set_proven_directive` defaults to true, so
  properties proven in one `prove` call assume each other. Use `jgu::dag_init` for per-node
  claims.
- **Job caps don't bind automatic engine mode.** Always name engines. `N` can still spawn
  `Ncustom` variants.
- **Undriven registers are free on every cycle.** Use `jgu::rigid` for a free constant.
- **Initial blocks are ignored (VERI-1060).** If they zero every register, use
  `reset -none -non_resettable_regs 0`.
- **`-batch` and `-no_gui` together fail (ESW082).** jgu uses `jg -batch -proj ... -tcl ...`.
- **Jasper shadows Tcl's `clock` command.** Use `jgu::now_ms` (`::tcl::clock::milliseconds`).
- **`info script` is empty under `jg -tcl`.** Use `jgu::script_dir`.
- **Procs in your own namespaces shadow built-in commands.** A proc named `info`, `trace` or
  `prove` inside your namespace hides the built-in there. Call Jasper commands as `::prove`.
- **A comment line ending in a backslash continues onto the next line.**
- **Multipliers are blackboxed automatically (WNL018).** Keep them with
  `elaborate -bbox_mul <width>`. Large arrays need `-bbox_a <entries>`.
- **Top-level signals are named without the top module's name** (for example `stopat q`).
- **A `-with_helpers` result is not standalone.** It only counts if the helpers are proven.
- **`unprocessed` means the property never ran.**
- **Trace cycles in `visualize` start at 1.**

## Tests

```sh
python3 -m unittest discover -s jasper-utils/tests
```

The unit tests run without a Jasper host. `test_jglib_tcl.py` runs `jglib.tcl` in `tclsh`
against stub Jasper commands, and is skipped if `tclsh` is not installed.

`examples/counter` is the live smoke test. Run it with `jgu run`, then check:

- `exit=0`;
- `results=cex:1,covered:1,proven:3`;
- `out/never5.vcd` exists.

## For orchestrators

Copy the folder into each agent's task directory and tell the agent about it:

```python
shutil.copytree(REPO / "jasper-utils", task_dir / "jasper-utils",
                ignore=shutil.ignore_patterns("__pycache__"))
```

Add this line to the agent's prompt: *"Reusable Jasper utilities are in `jasper-utils/`
(read its README.md); prefer them over writing your own runners and parsers."*
