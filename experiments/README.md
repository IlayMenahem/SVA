# Experiments

```
install.sh   installs EBMC 6.0, the Pi harness, and the Large Lemma Miners benchmarks
ebmc/        EBMC build (hw-cbmc, gitignored) and the recorded setup (setup.json)
pi/          Pi + lean-ctx campaign harness, its config, tests, and validation probes
runs/        one folder per run: config.json, prompt.md, run script, checkpoint, summaries
```

## Install

```sh
./install.sh
```

Needs Homebrew and lean-ctx. Put `OPENROUTER_API_KEY=...` in `pi/.env`.
Benchmarks land in `../datasets/raw/large-lemma-miners` at the paper's revision.

## Validate and run

```sh
cd pi
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python validation/validate_pi.py
.venv/bin/python campaign.py run --run-root ../runs/<date>-<name>
.venv/bin/python report.py --checkpoint ../runs/<date>-<name>/checkpoint.json
```

Git tracks only each run's `*.json`, `*.md`, `*.py`, and `figures/`. Bulk evidence
(`tasks/`, `requests/`, `clean-replay/`) stays local.
