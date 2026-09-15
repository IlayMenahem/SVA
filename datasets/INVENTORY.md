# Downloaded dataset sources

All nine sources are complete: 23,097 regular files, 2,235,916,301 bytes (2.24 GB), under Git-ignored `datasets/raw/`. Sizes use decimal MB, excluding Git metadata and symlinks.

| Source | Directory under `datasets/raw/` | MB | Revision |
|---|---|---:|---|
| HierSVA | `hiersva/` | 17.26 | `ef49c97247ba` |
| OpenTitan | `opentitan/` | 251.99 | `2bd27847c248` |
| HWSec-UNC | `hwsec-unc/` | 285.99 | `f5da736829b4` |
| riscv-formal | `riscv-formal/` | 1.86 | `4f29e83a8387` |
| VERT | `vert/` | 81.05 | `4a46c4295dae` |
| Verixa | `verixa/` | 158.87 | `02d137d97b28` |
| NVIDIA CVDP | `nvidia-cvdp/` | 1,434.37 | `5b807d945f6a` |
| VerilogEval current | `verilog-eval/current/` | 1.64 | `c498220d0a52` |
| VerilogEval release/1.0.0 | `verilog-eval/release-1.0.0/` | 1.67 | `4fa0ac4ed70f` |
| Large Lemma Miners | `large-lemma-miners/` | 1.23 | `ffc5b03e28b7` |

[manifest.json](manifest.json) records source URLs, full revisions, file counts, bytes, submodule commits, Hugging Face hashes, and download status; [validation.json](validation.json) records parsing results and Parquet metadata by file.

## Counts

| Source | Contents |
|---|---|
| HierSVA | 342 modules with final golden assertions; 353 assertion files including intermediate versions; 21 synthetic and 7 real bug variants; 27 module specifications. |
| OpenTitan | 3,938 SystemVerilog files; no fixed benchmark-task count. |
| HWSec-UNC | 119 documented properties: OR1200 71, Hack@DAC18 20, Hack@DAC19 11, Hack@DAC21 17. OR1200 submodule initialized at its recorded commit. |
| riscv-formal | 4 core integration directories, 13 check modules; no Git submodules or fixed task set. |
| VERT | 20,000 primary and 20,000 RAG-variant records; 28,032 records in 8 supplemental files. Overlapping variants cannot be summed as unique examples. |
| Verixa | 105,340 rows in all 6 published Parquet shards, including the additional 305-row shard. |
| NVIDIA CVDP | 22 JSONL files (versions 1.0.2 to 1.1.0), 40 Git bundles; 872 task-mode records in 1.1.0. Versions/modes overlap; per-file counts are in the manifest. |
| VerilogEval | Current: 156 tasks per mode (2 modes). Release/1.0.0: 156 Human, 143 Machine. Includes original examples and auxiliary files. |
| Large Lemma Miners | 109 benchmark SV files (78 main + 31 hard); 20 raw and 22 full few-shot examples. |

The Large Lemma Miners [revised paper](https://arxiv.org/html/2511.02521v2) reports 110 tasks; the complete pinned repository has 109. No tasks were added or removed. Separate Zenodo experiment caches are outside scope.

## Validation

Hugging Face sizes and SHA-256/LFS or Git-blob SHA-1 hashes match upstream metadata. Git object/LFS checks passed; working trees are clean, and revisions and submodules match recorded commits. All downloads and LFS contents are complete. JSON/JSONL parsing and all 6 Parquet metadata checks passed except for three upstream documentation files:

- OpenTitan `hw/vendor/pulp_riscv_dbg/doc/dmi_protocol.json` uses WaveDrom JavaScript object syntax.
- HWSec-UNC `hackatdac19/design/docs/search.json` and `hackatdac21/design/hackatdac21/piton/design/chip/tile/ariane/docs/search.json` are Jekyll/Liquid templates.

VERT's `VERT.json` and `VERT_withRAG.json` passed as JSONL. All raw files remain unchanged.

Resume/recheck pinned downloads with `python3 datasets/download.py` (requires Git, Git LFS, curl, Python, and network access). Regenerate validation and manifest counts with `uv run --with pyarrow --no-project python datasets/validate.py --finalize`. Validation uses PyArrow; no hardware toolchains were installed.
