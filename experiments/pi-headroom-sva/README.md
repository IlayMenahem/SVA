# Pi + Headroom SVA campaign

This directory runs the 31 `hard` benchmarks without modifying the benchmark
checkout. Every task gets an isolated Pi session, candidate store, work tree,
native EBMC reports, proof runs, ledger, and audit result.

## Reproduce the environment

```sh
brew install bison flex
npm ci
uv sync --frozen
git -C vendor/hw-cbmc submodule update --init --recursive
make -C vendor/hw-cbmc/src -j2 \
  YACC=/opt/homebrew/opt/bison/bin/bison \
  LEX=/opt/homebrew/opt/flex/bin/flex
.venv/bin/python setup/record_setup.py
```

The pinned versions are in `package-lock.json` and `uv.lock`. `setup/setup.json`
records the EBMC tag, CBMC submodule revision, compiler dependencies, platform,
and executable SHA-256.

## Validate locally

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s ../../accelerate-sva-proofs/tests -v
.venv/bin/python setup/validate_pi.py
python3 campaign.py prepare --run-root runs/campaign
```

For the Headroom round trip, start the local service and then run the probe:

```sh
HEADROOM_OFFLINE=true HEADROOM_TELEMETRY=off \
  .venv/bin/headroom proxy --port 8787 --no-cache \
  --no-subscription-tracking --stateless
node setup/headroom_roundtrip.mjs
```

## Run and report

```sh
export OPENROUTER_API_KEY='...'
python3 campaign.py run --run-root runs/campaign
python3 report.py --checkpoint runs/campaign/checkpoint.json
```

The runner uses two task workers, 12 minutes per task, 120 seconds per verifier
call, depth-30 bounded filtering, and a final clean unbounded replay. The shared
checkpoint enforces the four-hour deadline and reserves the final 30 minutes for
replay. Each provider request reserves worst-case cost before transmission; Pi
reconciles the recorded usage and charge afterward. The total cap is $25.

Pi uses only the five tools registered by `pi-extension.ts`: task reading,
candidate submission, EBMC invocation, evidence inspection, and retraction.
Pi's automatic compaction is disabled through RPC. Large evidence reads go to
Headroom's documented `/v1/compress` interface; classification and proof inputs
stay verbatim. Native evidence remains on disk and `inspect_evidence` can return
the exact original by artifact ID. Headroom failure aborts the tool call.

Without `OPENROUTER_API_KEY`, `prepare` and all verifier/Headroom validation can
run, while `run` records a paused status before any model request.
