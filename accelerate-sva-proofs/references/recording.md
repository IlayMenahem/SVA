# Recording and validation

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

Inputs are hashed before/after execution and again during validation. The manifest is caller-supplied: hashing cannot detect omitted inputs or transient changes restored before the final hash.

The recorder kills remaining POSIX process-group members on completion, timeout, or interruption. Detached workers, remote jobs, and batch schedulers need separate lifecycle management.

For remote provers:
- Measure CPU on the remote side (e.g. `/usr/bin/time -o` to a file in the run directory) so a killed session keeps its record.
- Run `ssh -n` with stdin from `/dev/null`; a lingering child holding stdin stalls the stream.
- Kill a session by its process group, never by `pkill` on a name, which also kills timing wrappers and other runs.
- Set the prover's job count explicitly in every session; automatic modes may exceed it.
- Check the run directory before launching; never repeat a recorded run unless its inputs changed.

Exit codes: `0` successful recording, `1` execution/recording failure, `2` invalid setup, `124` timeout, `130` interruption. None establishes proof status. Recorded wall time includes command execution and cleanup, excluding hashing and archival.

## Maintain a ledger

Copy `assets/proof-ledger.json` into the proof workspace and keep it in sync with the DAG.

| Field | Required content |
| --- | --- |
| `target` | Original target obligation ID. |
| `premises` | Supplied premises: unique `id`, `kind: "supplied"`, `statement`, `source`, `scope`. |
| `obligations` | Unique `id`, `statement`, `scope`, `dependencies` (obligation IDs), `premises` (supplied premise IDs). |
| `transformations` | Unique `id`, `kind`, `description`, `applies_to` (using obligation IDs), `obligations` (preservation/interface IDs). Each use must depend on these obligations. |

Obligations need no evidence of their own; the replay proves them. Unused candidates may stay in the ledger but cannot form cycles or hold invalid references.

## Validate a proof

A proof is accepted only when this passes:

```bash
python3 /path/to/accelerate-sva-proofs/scripts/validate_proof.py /path/to/project/proof-ledger.json
```

The replay script must write a results file, archived with `--report`, listing every replayed property:

```json
{"properties": [
  {"id": "target", "kind": "assert", "status": "proven", "engine": "Hp", "assumed": ["helper"]},
  {"id": "cov_target_pre", "kind": "cover", "status": "covered", "engine": "Ht", "assumed": []}
]}
```

`id` matches ledger obligation IDs, and `assumed` lists the obligations and supplied premises enabled as assumptions while proving it. Add the replay to the ledger:

```json
"replay": {
  "run": "proof-runs/replay-001/run.json",
  "run_sha256": "SHA-256 printed by the recorder",
  "proof_kind": "unbounded",
  "evidence": {"file": "reports/000-results.json", "sha256": "hash from run.json evidence", "locator": "replay results file"},
  "context_review": "Clean prover state, original parameters, one engine per node",
  "covers": ["cov_target_pre"]
}
```

Run paths resolve relative to the ledger; evidence paths stay inside the run directory. Verify the recorded tool version against the executable.

The validator requires a valid DAG, a valid replay record with current inputs, every obligation in the target's closure `proven` in that one replay with `assumed` within its declared dependencies and premises, and every listed cover (at least one) `covered`. It trusts the results file to reflect the prover's output; formal validity remains `not_certified`, so apply the semantic checks in [correctness](correctness.md). Exit `0` means accepted.
