"""Named, reproducible experiment plans; orchestration without changing retrieval."""
import json
import math
from pathlib import Path
import re
import shlex
import subprocess
import sys

CATALOG = 'configs/experiments.json'
REGISTRY = 'experiments/registry.json'


def load_catalog(root, path=CATALOG):
    root = Path(root)
    catalog = json.loads((root / path).read_text())
    if catalog.get('schema_version') != 1:
        raise ValueError('Unsupported experiment catalog version')
    seen = set()
    for spec in catalog['experiments']:
        run_id = spec['experiment_id']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', run_id) or run_id in seen:
            raise ValueError('Experiment IDs must be unique, safe directory names')
        seen.add(run_id)
        if spec['method'] not in ('uniform','diversity'):
            raise ValueError('Only uniform and diversity sampling + OpenCLIP are implemented')
        interval = spec.get('interval_seconds')
        if spec['method']=='uniform' and (isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0):
            raise ValueError('Sampling interval must be finite and positive')
        if spec['method']=='diversity' and (type(spec.get('max_frames')) is not int or spec['max_frames']<=0):
            raise ValueError('Diversity requires a positive integer max_frames budget')
        if spec['method']=='uniform' and spec.get('max_frames') is not None:
            raise ValueError('Uniform catalog entries use interval_seconds; omit max_frames')
        if spec['method']=='diversity' and spec.get('interval_seconds') is not None:
            raise ValueError('Diversity uses all eligible candidates; omit interval_seconds')
        for field in ('threads', 'batch_size'):
            if type(spec[field]) is not int or spec[field] <= 0:
                raise ValueError(f'{field} must be a positive integer')
        for field in ('footage', 'dataset_manifest', 'queries'):
            if not isinstance(spec[field], str) or not spec[field].strip():
                raise ValueError(f'{field} must be a nonempty path')
    return catalog


def output_paths(spec):
    run_id = spec['experiment_id']
    return {'evidence': f'experiments/{run_id}',
            'index': f'indexes/{run_id}/index.npz',
            'results': f'results/retrieval/{run_id}'}


def status(root, spec):
    root = Path(root)
    registry = json.loads((root / REGISTRY).read_text())
    entry = next((e for e in registry['experiments']
                  if e['experiment_id'] == spec['experiment_id']), None)
    if entry:
        if entry.get('benchmark_record'):
            record = json.loads((root / entry['benchmark_record']).read_text())
            method = record['method']
            recorded_video = (root / record['source']['video']['path']).resolve()
            changed = (recorded_video != (root / spec['footage']).resolve()
                       or method['sampling'].get('name') != spec['method']
                       or method['sampling'].get('interval_seconds') != spec.get('interval_seconds')
                       or method['sampling'].get('max_frames') != spec.get('max_frames')
                       or method['encoder'].get('threads') != spec['threads']
                       or method.get('inference_settings', {}).get('batch_size') != spec['batch_size'])
            if changed:
                return 'configuration differs from saved run; use a new ID'
        return entry['status']
    paths = output_paths(spec)
    if any(((root / path).parent if key == 'index' else root / path).exists()
           for key, path in paths.items()):
        return 'incomplete/unregistered (inspect saved evidence)'
    return 'planned'


def command(spec, python=None):
    paths = output_paths(spec)
    args = [python or sys.executable, 'scripts/run_development_experiment.py',
            '--dataset-manifest', spec['dataset_manifest'],
            '--index', paths['index'], '--results', paths['results'],
            '--output', paths['evidence'], '--method',spec['method'],
            '--batch-size', str(spec['batch_size']), '--threads', str(spec['threads']),
            '--queries', spec['queries']]
    if spec['method']=='uniform':
        args+=['--interval',str(spec['interval_seconds'])]
    else:
        args+=['--max-frames',str(spec['max_frames'])]
    return args


def validate_inputs(root, spec):
    root = Path(root)
    for field in ('footage', 'dataset_manifest', 'queries'):
        if not (root / spec[field]).is_file():
            raise FileNotFoundError(f'{field}: {spec[field]}')
    manifest = json.loads((root / spec['dataset_manifest']).read_text())
    if (root / manifest['video']['path']).resolve() != (root / spec['footage']).resolve():
        raise ValueError('Catalog footage does not match the dataset manifest video path')
    queries = json.loads((root / spec['queries']).read_text())['queries']
    if not queries or any(not isinstance(q.get('text'), str) or not q['text'].strip() for q in queries):
        raise ValueError('Query file must contain nonempty query texts')
    ids = [q['id'] for q in queries]
    if len(set(ids)) != len(ids):
        raise ValueError('Query IDs must be unique')


def describe(root, spec):
    return {**spec, 'status': status(root, spec), 'outputs': output_paths(spec),
            'encoder': 'OpenCLIP ViT-B-32 / laion2b_s34b_b79k; CPU, fp32, seed 0',
            'measurements': '1 build; 2 fresh processes per query; 3 resident rounds; previews verified',
            'command': 'HF_HUB_OFFLINE=1 ' + shlex.join(command(spec))}


def run(root, spec, catalog_path=CATALOG):
    """Run one fresh experiment, then register successful evidence and refresh tables."""
    root = Path(root)
    validate_inputs(root, spec)
    paths = output_paths(spec)
    registry = json.loads((root / REGISTRY).read_text())
    if any(e['experiment_id'] == spec['experiment_id'] for e in registry['experiments']):
        raise FileExistsError('This experiment is already registered; use a new experiment ID for a repeat')
    for path in paths.values():
        # Reject an existing index directory too, even if its index is absent.
        candidate = (root / path).parent if path == paths['index'] else root / path
        if candidate.exists():
            raise FileExistsError(f'Choose a new experiment ID; output already exists: {candidate}')
    print(json.dumps(describe(root, spec), indent=2), flush=True)
    completed = subprocess.run(command(spec), cwd=root, check=False)
    evidence_dir = root / paths['evidence']
    if evidence_dir.exists():
        (evidence_dir / 'run_config.json').write_text(json.dumps({
            'catalog': catalog_path, 'experiment': spec,
            'command': shlex.join(command(spec)), 'returncode': completed.returncode}, indent=2) + '\n')
    if completed.returncode:
        raise RuntimeError(f'Experiment failed (exit {completed.returncode}); inspect {paths["evidence"]}. No completed row added.')
    report = json.loads((evidence_dir / 'experiment.json').read_text())
    if report.get('passed') is not True:
        raise RuntimeError('Verification did not pass; run was not registered as completed')
    record_path = f'{paths["evidence"]}/benchmark_record.json'
    record = json.loads((root / record_path).read_text())
    entry = {'experiment_id': spec['experiment_id'], 'label': spec['label'],
             'status': 'completed', 'benchmark_record': record_path,
             'evidence': f'{paths["evidence"]}/experiment.json',
             'notes': f'Run from {catalog_path}; configuration snapshot in {paths["evidence"]}/run_config.json'}
    from .reporting import experiment_row, generate, terminal_results
    experiment_row(entry, record, report)  # Validate before updating the registry.
    # Re-read after a potentially long run so intervening registry edits are preserved.
    registry = json.loads((root / REGISTRY).read_text())
    if any(e['experiment_id'] == spec['experiment_id'] for e in registry['experiments']):
        raise FileExistsError('Experiment ID was registered while running; inspect evidence before registering')
    registry['experiments'].append(entry)
    target = root / REGISTRY
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(registry, indent=2) + '\n')
    temporary.replace(target)
    generate(root)
    print(terminal_results(root, spec['experiment_id']))
    print('Completed and added to experiments/summary.csv and docs/RESULTS_OVERVIEW.md')
