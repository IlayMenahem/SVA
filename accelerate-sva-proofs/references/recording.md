# Recording and auditing

## Record a run

Create a manifest listing all proof-relevant RTL, includes, assertions, scripts, source lists, and configuration. Record environment-dependent settings explicitly, without secrets.

```json
{
  "files": ["rtl/design.sv", "formal/target.sv", "formal/run-proof.sh"],
  "settings": {"top": "design", "engine": "actual engine and mode"}
}
```

Use the project's synchronous proof command:

```bash
python3 /path/to/accelerate-sva-proofs/scripts/record_run.py \
  --cwd /path/to/project \
  --manifest /path/to/project/formal/inputs.json \
  --output /path/to/project/proof-runs/candidate-001 \
  --timeout 300 \
  --tool-version 'actual prover and version' \
  -- /bin/sh formal/run-proof.sh
```

Arguments after `--` are literal; shell syntax requires an explicit shell. Manifest/output paths resolve from the invocation directory; manifest entries and `--report` paths resolve from `--cwd`.

The output directory must be new. It contains `run.json`, stdout/stderr logs, and reports requested with `--report path`. Report paths must not exist before execution. Retain exact source snapshots and any native proof databases needed for replay.

Inputs are hashed before/after execution and again during audit. The manifest is caller-supplied: hashing cannot detect omitted inputs or transient changes restored before the final hash.

The recorder kills remaining POSIX process-group members on completion, timeout, or interruption. Detached workers, remote jobs, and batch schedulers need separate lifecycle management.

Exit codes: `0` successful recording, `1` execution/recording failure, `2` invalid setup, `124` timeout, `130` interruption. None establishes proof status. Recorded wall time includes command execution and cleanup, excluding hashing and archival.

## Maintain a ledger

Copy `assets/proof-ledger.json` into the proof workspace.

| Field | Required content |
| --- | --- |
| `target` | Original target obligation ID. |
| `premises` | Supplied premises: unique `id`, `kind: "supplied"`, `statement`, `source`, `scope`. |
| `obligations` | Unique `id`, `statement`, `scope`, `dependencies` (obligation IDs), `premises` (supplied premise IDs), `outcome`. |
| `transformations` | Unique `id`, `kind`, `description`, `applies_to` (using obligation IDs), `obligations` (preservation/interface IDs). Each use must depend on these obligations. |

Outcomes are `unproved`, `proved`, `failed`, `timeout`, `bounded`, `unknown`, or `error`. For each `proved` entry, add:

```json
{
  "proof_kind": "unbounded",
  "run": "proof-runs/helper-001/run.json",
  "run_sha256": "SHA-256 printed by the recorder",
  "evidence": {
    "file": "stdout.log",
    "sha256": "matching hash from run.json evidence",
    "locator": "Property identifier and report lines establishing the result"
  },
  "context_review": "Actual assumptions, clock/reset, property identity, proof mode, and dependency compatibility"
}
```

Run paths resolve relative to the ledger; evidence paths stay inside the run directory. Verify the recorded tool version against the executable. Keep entries tied to their exact inputs and immutable run records.

## Audit completion

```bash
python3 /path/to/accelerate-sva-proofs/scripts/audit_proof.py /path/to/project/proof-ledger.json
```

The audit checks DAG structure, every entry labeled `proved`, evidence integrity, and current input hashes. All target dependencies must be proved at completion, regardless of run order. Unused candidates may remain unresolved but cannot contain cycles or invalid references.

Exit `0` means bookkeeping passed; exit `1` means it failed. The result always includes `formal_validity: "not_certified"`; apply the semantic checks in [correctness](correctness.md).
