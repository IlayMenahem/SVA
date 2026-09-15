#!/usr/bin/env python3
"""Validate raw structured files and record counts without rewriting upstream data."""
import collections
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent

EXPECTED = {
    'hiersva': ['golden', 'rtl', 'buggy_rtl', 'buggy_rtl2', 'spec', 'json'],
    'opentitan': ['hw/ip', 'hw/dv', 'LICENSE'],
    'hwsec-unc': ['or1200/buggy-or1200', 'or1200/properties.md', 'hackatdac18/properties.md', 'hackatdac19/properties.md', 'hackatdac21/properties.md'],
    'riscv-formal': ['checks', 'insns', 'cores', 'COPYING'],
    'vert': ['VERT/VERT.json', 'Supplimental_datasets/VERT_withRAG.json'],
    'verixa': ['data', 'README.md'],
    'nvidia-cvdp': ['LICENSE', 'NOTICE', 'cvdp_v1.1.0_agentic_heavy_code_generation_public'],
    'verilog-eval': ['current/dataset_spec-to-rtl', 'current/dataset_code-complete-iccad2023', 'release-1.0.0/data/VerilogEval_Human.jsonl', 'release-1.0.0/data/VerilogEval_Machine.jsonl'],
    'large-lemma-miners': ['benchmarks/main_experiment', 'benchmarks/hard', 'fewshot/examples_raw', 'fewshot/examples_full'],
}


def counts(name, root, result):
    structured = result['structured_files']
    if name == 'hiersva':
        return {'golden_modules': len(list((root/'golden').rglob('final/assertions.v'))),
                'all_assertion_files_including_intermediate_versions': len(list((root/'golden').rglob('assertions.v'))),
                'synthetic_bug_variants': len(list((root/'buggy_rtl').rglob('*.sv'))),
                'real_bug_variants': len(list((root/'buggy_rtl2').rglob('*.sv'))),
                'module_specifications': len(list((root/'spec').glob('*.md'))) - 1}
    if name == 'hwsec-unc':
        return {'documented_properties_by_design': {p.parent.name: len(re.findall(r'^\|\s*p?\d+\s*\|', p.read_text(), re.M)) for p in root.glob('*/properties.md')}}
    if name == 'opentitan':
        return {'systemverilog_files': result['extensions'].get('.sv', 0),
                'note': 'Repository corpus; file count is not a benchmark-task count.'}
    if name == 'riscv-formal':
        return {'core_integration_directories': len([p for p in (root/'cores').iterdir() if p.is_dir()]),
                'check_modules': len(list((root/'checks').glob('*_check.sv'))),
                'note': 'Framework corpus; no fixed task count. No Git submodules in pinned tree.'}
    if name == 'vert':
        return {'records_by_file': {f['file']: f.get('records', f.get('top_level_items')) for f in structured},
                'note': 'Supplemental variants overlap; these counts are not unique examples.'}
    if name == 'verixa':
        return {'parquet_shards': len(structured), 'rows': sum(f['rows'] for f in structured)}
    if name == 'nvidia-cvdp':
        return {'records_by_file': {f['file']: f['records'] for f in structured},
                'git_bundles': len(list(root.rglob('*.bundle'))),
                'note': 'Published versions and task modes overlap; do not sum as unique tasks.'}
    if name == 'verilog-eval':
        return {'current_tasks_by_mode': {p.name: len(list(p.glob('*_prompt.txt'))) for p in (root/'current').glob('dataset_*')},
                'release_1_0_0_tasks': {f['file']: f['records'] for f in structured if f['file'].startswith('release-1.0.0/data/VerilogEval_')}}
    if name == 'large-lemma-miners':
        main = len(list((root/'benchmarks/main_experiment').glob('*.sv')))
        hard = len(list((root/'benchmarks/hard').glob('*.sv')))
        return {'main_experiment_tasks': main, 'hard_tasks': hard, 'total_benchmark_tasks': main + hard,
                'fewshot_raw_examples': len(list((root/'fewshot/examples_raw').glob('*.sv'))),
                'fewshot_full_examples': len(list((root/'fewshot/examples_full').glob('*.txt'))),
                'paper_reported_tasks': 110, 'paper_url': 'https://arxiv.org/html/2511.02521v2',
                'note': 'Pinned published repository contains 109 benchmark SV files (78 + 31), whereas revised paper reports 110. All upstream files retained; no trimming or invented task.'}


def files_under(path):
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != '.git']
        for name in sorted(files):
            p = Path(root) / name
            if name != '.git' and not p.is_symlink():
                yield p


def validate(entry):
    root = BASE.parent / entry['local_directory']
    result = {'extensions': {}, 'structured_files': [], 'parse_errors': [], 'top_level': sorted(p.name for p in root.iterdir() if p.name != '.git')}
    extensions = collections.Counter()
    for p in files_under(root):
        extensions[p.suffix] += 1
        rel = str(p.relative_to(root))
        fmt = p.suffix
        if fmt == '.gz':
            fmt = Path(p.stem).suffix
        if fmt not in ('.json', '.jsonl', '.parquet'):
            continue
        info = {'file': rel, 'format': fmt[1:]}
        try:
            if fmt == '.parquet':
                import pyarrow.parquet as pq
                pf = pq.ParquetFile(p)
                info.update(rows=pf.metadata.num_rows, row_groups=pf.metadata.num_row_groups,
                            columns=pf.schema.names)
            else:
                opener = gzip.open if p.suffix == '.gz' else open
                with opener(p, 'rt', encoding='utf-8-sig') as f:
                    if fmt == '.jsonl':
                        count = 0
                        for number, line in enumerate(f, 1):
                            if line.strip():
                                json.loads(line)
                                count += 1
                        info['records'] = count
                    else:
                        try:
                            obj = json.load(f)
                        except json.JSONDecodeError:
                            # VERT stores JSONL under .json filenames.
                            f.seek(0)
                            count = 0
                            for line in f:
                                if line.strip():
                                    json.loads(line)
                                    count += 1
                            info.update(format='jsonl', records=count)
                            result['structured_files'].append(info)
                            continue
                        info['top_level_type'] = type(obj).__name__
                        info['top_level_items'] = len(obj) if isinstance(obj, (dict, list)) else 1
                        if isinstance(obj, dict):
                            info['list_lengths'] = {k: len(v) for k, v in obj.items() if isinstance(v, list)}
            result['structured_files'].append(info)
        except Exception as exc:
            result['parse_errors'].append({'file': rel, 'error': str(exc)})
    result['extensions'] = dict(extensions.most_common())
    result['missing_expected_paths'] = [p for p in EXPECTED[entry['name']] if not (root/p).exists()]
    result['benchmark_counts'] = counts(entry['name'], root, result)
    for error in result['parse_errors']:
        if error['file'].endswith('/docs/search.json'):
            error['classification'] = 'Upstream Jekyll/Liquid template, not literal JSON.'
        elif error['file'] == 'hw/vendor/pulp_riscv_dbg/doc/dmi_protocol.json':
            error['classification'] = 'Upstream WaveDrom JavaScript object syntax, not strict JSON.'
    if entry['kind'] == 'git':
        repos = [root/'current', root/'release-1.0.0'] if entry['name'] == 'verilog-eval' else [root]
        result['git_worktrees'] = []
        for repo in repos:
            status = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=repo, text=True).strip()
            revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
            expected = entry['release_1_0_0']['revision'] if repo.name == 'release-1.0.0' else entry['revision']
            result['git_worktrees'].append({'path': str(repo.relative_to(BASE.parent)), 'clean': not status, 'revision_matches': revision == expected})
    return result


if __name__ == '__main__':
    manifest = json.loads((BASE / 'manifest.json').read_text())
    if '--status' in sys.argv:
        for entry in manifest['sources']:
            root = BASE.parent / entry['local_directory']
            files = list(files_under(root))
            print(entry['name'], entry['download_status'], len(files), sum(p.stat().st_size for p in files), entry.get('error', '') if entry['download_status'] in ('incomplete', 'inaccessible') else '')
        sys.exit()
    results = {}
    for entry in manifest['sources']:
        root = BASE.parent / entry['local_directory']
        if not root.exists():
            continue
        result = validate(entry)
        results[entry['name']] = result
        print(entry['name'], 'files:', sum(result['extensions'].values()), 'structured:', len(result['structured_files']), 'parse_errors:', result['parse_errors'], flush=True)
    (BASE / 'validation.json').write_text(json.dumps({'validated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'sources': results}, indent=2) + '\n')
    if '--finalize' in sys.argv:
        if any(e['download_status'] != 'complete' for e in manifest['sources']):
            raise SystemExit('Downloads are not all complete; manifest not finalized.')
        for entry in manifest['sources']:
            result = results[entry['name']]
            if result['missing_expected_paths'] or any(not r['clean'] or not r['revision_matches'] for r in result.get('git_worktrees', [])):
                raise SystemExit(f'Content verification failed: {entry["name"]}')
            if any('classification' not in error for error in result['parse_errors']):
                raise SystemExit(f'Unexplained parsing errors: {entry["name"]}')
            entry['benchmark_counts'] = result['benchmark_counts']
            entry['validation'] = {'report': 'datasets/validation.json', 'expected_paths_present': True,
                                   'structured_files_validated': len(result['structured_files']),
                                   'upstream_format_exceptions': result['parse_errors']}
            if entry['name'] == 'verilog-eval':
                for key, directory in [('current_snapshot', 'current'), ('release_1_0_0', 'release-1.0.0')]:
                    detail = entry.setdefault(key, {'revision': entry['revision'], 'local_directory': entry['local_directory'] + '/current'})
                    files = list(files_under(BASE.parent / entry['local_directory'] / directory))
                    detail.update(file_count=len(files), total_size_bytes=sum(p.stat().st_size for p in files), download_status='complete')
        manifest['validated_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        (BASE/'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
