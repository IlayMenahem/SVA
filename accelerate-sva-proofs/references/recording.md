# Recording runs and auditing proof state

These helpers preserve evidence and check bookkeeping. They do not parse SVA, interpret vendor reports, or validate abstraction semantics. No installed prover is required to use the auditor or run the helper tests.

## Record a run

Create a JSON manifest with a nonempty `files` list and optional `settings` object. List every proof-relevant RTL/include file, assertion, script, source list, parameter file, and tool configuration. Paths resolve relative to `--cwd`. Record relevant environment-dependent settings explicitly, without secrets; the recorder inherits the environment but does not dump it. Use a wrapper/configuration file to make those settings reproducible and include it in the manifest.

```json
{
  "files": ["rtl/design.sv", "formal/target.sv", "formal/run-proof.sh"],
  "settings": {"top": "design", "engine": "record the actual engine and mode"}
}
```

Invoke from a shell using the installed skill's absolute path. Here `/path/to/accelerate-sva-proofs` and `/path/to/project` denote your chosen locations; `run-proof.sh` is the project's existing synchronous prover wrapper, not a bundled script.

```bash
python3 /path/to/accelerate-sva-proofs/scripts/record_run.py \
  --cwd /path/to/project \
  --manifest /path/to/project/formal/inputs.json \
  --output /path/to/project/proof-runs/baseline-001 \
  --timeout 300 \
  --tool-version 'actual backend and version' \
  -- /bin/sh formal/run-proof.sh
```

The timeout above is an example, not a default. Arguments after `--` are passed directly without shell expansion; shell syntax works only when you explicitly invoke a shell. `--manifest` and `--output` resolve from the recorder's invocation directory, while manifest entries and repeated `--report` arguments resolve from `--cwd`.

Use `--report formal/new-run/result.txt` to archive a vendor report after execution. The report path must not exist before the run; configure the prover to write to a fresh location. This avoids accepting a previous run's report accidentally. Archive reports needed to establish property identity and unbounded proof status, not just a summary count. Keep full native proof databases separately when needed for replay.

The output directory must be new. It contains `run.json`, `stdout.log`, `stderr.log`, and any archived reports. Inputs are hashed before and after the command; listed inputs changed during execution invalidate the recording for proof reuse. Files are hashed again during audit. Capture source snapshots or retain the exact recorded checkout so old proof inputs remain accessible.

The recorder uses POSIX process groups and kills the run's remaining group members on completion, timeout, or interruption. Use a synchronous foreground command; detached workers, batch schedulers, remote jobs, and workers starting their own sessions need backend-native lifecycle management and are outside this timeout guarantee. Do not wrap an interactive session or service you intend to keep running.

Exit codes: `0` means successful execution and intact recording, `1` means execution/recording failure or changed inputs, `2` means invalid setup, `124` means timeout, and `130` means interruption. None means a formal proof. `run.json` retains the actual command exit code and status. Wall time covers command execution and cleanup, excluding hashing and report archival; measure overall optimization wall time separately. CPU time and agent cost are not inferred.

## Maintain a ledger

Copy `assets/proof-ledger.json` into the proof workspace and fill the original target and context. The initial template is deliberately unproved and must fail closure audit.

The version-1 ledger has these fields:

| Field | Meaning |
| --- | --- |
| `target` | ID of the original target obligation. |
| `premises` | Supplied premises with unique `id`, `kind: "supplied"`, `statement`, `source`, and `scope`. Generated assumptions belong in obligations. |
| `obligations` | Unique `id`, `statement`, `scope`, `dependencies` (obligation IDs), `premises` (supplied premise IDs), and `outcome`. Parent-to-child edges encode all generated facts used. |
| `transformations` | Unique `id`, `kind`, `description`, `applies_to` (using obligation IDs), and `obligations` (required preservation/interface obligation IDs). Each using obligation must explicitly depend on all these requirements. |

Outcomes are `unproved`, `proved`, `failed`, `timeout`, `bounded`, `unknown`, or `error`. Only `proved` can support a parent. For each proved obligation, add:

```json
{
  "proof_kind": "unbounded",
  "run": "proof-runs/helper-001/run.json",
  "run_sha256": "SHA-256 printed by the recorder",
  "evidence": {
    "file": "stdout.log",
    "sha256": "matching hash from run.json evidence",
    "locator": "Exact property identifier and report lines establishing the unbounded result"
  },
  "context_review": "Document the actual assumptions, clock/reset, property identity, proof mode, and why dependency contexts are compatible."
}
```

`run` resolves relative to the ledger; evidence paths resolve inside that run directory and cannot escape it. The auditor verifies the run-record digest, archived evidence hashes, and current input hashes. The locator and context review must be substantive human/agent interpretations of the real report; the script can check their presence only.

Recording the tool version is optional for exploratory runs but required by the auditor for entries labeled proved. The recorder stores `--tool-version` verbatim; verify it against the actual executable/version report.

Record helpers in separate completed runs before launching parents that assume them. This auditor deliberately requires dependency completion timestamps to precede parent start times. A single backend invocation that internally proves a dependency graph needs backend-specific evidence and is not supported by this portable chronology check. Use a consistent local clock when recording related runs.

Keep successful ledger entries tied to their exact candidate context. Do not repoint old entries to modified sources or overwrite their run records. When a dependency or context changes, mark affected entries `unproved` and re-run them. Changes to the ledger alone do not alter the prover's actual assumptions; check the scripts and reports as well.

## Audit and interpret the result

```bash
python3 /path/to/accelerate-sva-proofs/scripts/audit_proof.py /path/to/project/proof-ledger.json
python3 -m unittest discover -s /path/to/accelerate-sva-proofs/tests -v
```

The audit exits `0` only if bookkeeping passes, otherwise `1`. Its JSON always includes `formal_validity: "not_certified"`. It checks all graph structure and all entries labeled proved, and requires every obligation in the target closure to be proved. Unused speculative entries may remain unresolved, but cannot contain cycles or invalid references.

Input manifests are caller-supplied and cannot be proven complete by hashing. The scripts do not detect transient input changes restored before the final hash, capture tool binaries automatically, authenticate reports, or determine whether assumptions are justified. Run against a stable source snapshot, record tool identity, inspect the actual proof context, and perform the semantic checks in [correctness.md](correctness.md).
