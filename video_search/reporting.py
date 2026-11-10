"""Metadata-only experiment tables. Never load models, videos, or saved indexes."""
import csv
from fractions import Fraction
import json
import math
import os
from pathlib import Path

INCLUDED_STATUSES = {'current', 'completed'}
STATUSES = INCLUDED_STATUSES | {'superseded', 'failed'}
HISTORICAL_HARDWARE_REASON = 'Not recorded at run time; current hardware audit is not historical evidence'
STAGE_NAMES = ('input_fingerprint', 'dataset_validation', 'video_probe', 'timeline_decoding',
               'selection', 'diversity_selection', 'source_integrity_recheck', 'eligibility_filter', 'selected_frame_decoding', 'rgb_to_pil',
               'image_encoding_including_preprocess', 'index_arrays_and_validation',
               'model_fingerprint', 'index_persistence', 'output_fingerprint')


def read_json(root, path):
    return json.loads((Path(root) / path).read_text())


def summary_stats(value):
    """A missing sample set stays unknown; zero is a legitimate measured value."""
    if not isinstance(value, dict) or not value.get('count'):
        return {'count': 0, 'median': None, 'sample_stddev': None, 'minimum': None,
                'maximum': None, 'p95': None, 'p95_reason': 'No timing samples recorded'}
    if len(value.get('samples', [])) != value['count']:
        raise ValueError('Latency sample count does not match saved observations')
    for number in value['samples']:
        if not math.isfinite(number) or number < 0:
            raise ValueError('Invalid saved timing sample')
    return value


def json_cell(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def metric_value(value):
    if isinstance(value, dict):
        return value.get('value') if value.get('status') == 'measured' else None
    return value


def metric_reason(value, fallback):
    return value.get('reason', fallback) if isinstance(value, dict) else fallback


def experiment_row(spec, record, evidence):
    if record['experiment_id'] != spec['experiment_id']:
        raise ValueError('An audit must identify the actual experiment; it cannot create another run')
    if record.get('evidence_path') != spec['evidence']:
        raise ValueError('Registry and benchmark record disagree on source evidence')
    if evidence.get('passed') is not True or any(c.get('returncode', 0) != 0 for c in evidence.get('commands', [])):
        raise ValueError('A failed or unverified run cannot be included as a completed comparison')
    source, method = record['source'], record['method']
    video, encoder = source['video'], method['encoder']
    timing, memory, storage = record['timing'], record['memory'], record['storage']
    accuracy = record.get('ground_truth_accuracy', {})
    hit = accuracy.get('query_hit_at_5') if accuracy.get('status') == 'measured' else None
    evaluated = accuracy.get('evaluated_query_count') if hit is not None else None
    if hit is not None and (not math.isfinite(hit) or not 0 <= hit <= 1 or not isinstance(evaluated, int) or evaluated <= 0):
        raise ValueError('Hit@5 requires a valid fraction and a positive annotated query count')
    hardware = record['environment'].get('hardware_at_run', {})
    hardware_missing = hardware.get('status') == 'unavailable'
    cpu = None if hardware_missing else metric_value(hardware.get('cpu_model'))
    ram = None if hardware_missing else metric_value(hardware.get('physical_ram_bytes'))
    meta = evidence.get('index_metadata', {})
    stages = timing.get('indexing_stage_seconds', {})
    stage_missing = not isinstance(stages, dict) or stages.get('status') == 'unavailable' or not stages
    stage_reason = metric_reason(stages, 'No stage profile recorded') if stage_missing else ''
    query_peaks = [p for p in memory.get('fresh_query_peak_process_ram_bytes', []) if p is not None]
    row = {
        'experiment_id': spec['experiment_id'], 'status': spec['status'], 'label': spec['label'],
        'camera_id': source.get('camera_id'), 'dataset_id': source.get('dataset_id'),
        'video_path': video.get('path'), 'video_sha256': video.get('sha256'),
        'clip_duration_s': video.get('duration_seconds'), 'source_frame_count': video.get('decoded_frames'),
        'width_px': video.get('width'), 'height_px': video.get('height'), 'stored_fps': video.get('fps'),
        'sampling_method': method['sampling'].get('name'),
        'sampling_interval_s': method['sampling'].get('interval_seconds'),
        'retained_frame_budget': method['sampling'].get('max_frames'),
        'candidate_frames_encoded': meta.get('candidate_frames_encoded'),
        'sampling_parameters_json': json_cell(method['sampling']),
        'representation': method.get('representation'), 'model': encoder.get('model'),
        'checkpoint': encoder.get('pretrained'), 'weights_sha256': encoder.get('weights_sha256'),
        'indexed_item_kind': method['indexed_items']['kind'], 'indexed_item_count': method['indexed_items']['count'],
        'embedding_dimensions': method.get('embedding_dimension'), 'dtype': method.get('dtype'),
        'caption_lengths_json': json_cell(method.get('caption_lengths', {'status': 'not_applicable', 'reason': 'Embeddings-only baseline; no captions stored'})) if method.get('representation') == 'OpenCLIP image/text embeddings' else json_cell(method.get('caption_lengths', {'status': 'unavailable', 'reason': 'Not reported'})),
        'index_bytes': storage.get('primary_index_bytes'), 'index_bytes_status': storage.get('primary_status'),
        'storage_breakdown_json': json_cell(storage.get('measured_bytes_by_role', {})),
        'storage_missing_json': json_cell(record.get('storage_unmeasured', {})),
        'core_build_s': meta.get('indexing_seconds'), 'model_loading_s': meta.get('model_load_seconds'),
        'throughput_input_video_hours_per_wall_hour': timing.get('source_video_hours_per_wall_hour'),
        'stages_status': 'unavailable' if stage_missing else 'measured', 'stages_reason': stage_reason,
        'indexing_peak_process_ram_bytes': memory.get('index_peak_process_ram_bytes'),
        'query_peak_process_ram_max_bytes': max(query_peaks) if query_peaks else None,
        'memory_scope': memory.get('scope'),
        'accelerator_peak_memory_bytes': metric_value(memory.get('accelerator_peak_memory')),
        'accelerator_peak_memory_reason': metric_reason(memory.get('accelerator_peak_memory'), 'Not recorded'),
        'system_peak_ram_bytes': metric_value(memory.get('system_wide_peak_ram')),
        'system_peak_ram_reason': metric_reason(memory.get('system_wide_peak_ram'), 'Not recorded'),
        'cpu_model': cpu, 'cpu_model_reason': '' if cpu is not None else metric_reason(hardware.get('cpu_model'), HISTORICAL_HARDWARE_REASON),
        'physical_ram_bytes': ram, 'physical_ram_reason': '' if ram is not None else metric_reason(hardware.get('physical_ram_bytes'), HISTORICAL_HARDWARE_REASON),
        'device': encoder.get('device'), 'threads': encoder.get('threads'), 'seed': encoder.get('seed'),
        'inference_settings_json': json_cell(method.get('inference_settings', {})),
        'software_versions_json': json_cell(record['environment'].get('software_at_run', {})),
        'availability_protocol_json': json_cell(source.get('availability')),
        'valid_source_intervals_json': json_cell(source.get('valid_source_intervals')),
        'query_hit_at_5': hit, 'quality_evaluated_queries': evaluated,
        'quality_status': accuracy.get('status', 'unavailable'),
        'quality_reason': accuracy.get('reason', 'Not reported') if hit is None else '',
        'benchmark_repetitions_json': json_cell(record.get('repetitions', {})),
        'measurement_boundaries_json': json_cell(record.get('measurement_boundaries', {})),
        'record_path': spec['benchmark_record'], 'evidence_path': spec['evidence'],
    }
    for prefix, name in [('indexing', 'indexing_end_to_end_seconds'),
                         ('fresh_query_with_previews', 'fresh_process_query_with_previews_seconds'),
                         ('warm_query_without_previews', 'resident_query_without_previews_seconds')]:
        stats = summary_stats(timing.get(name))
        row[prefix + '_n'] = stats['count']
        for key in ('median', 'sample_stddev', 'minimum', 'maximum', 'p95'):
            row[prefix + '_' + key + '_s'] = stats.get(key)
        row[prefix + '_p95_reason'] = stats.get('p95_reason', '')
    for name in STAGE_NAMES:
        row['stage_' + name + '_s'] = None if stage_missing else stages.get(name, {}).get('seconds')
    row['stage_timings_json'] = json_cell(stages)
    return row


def collect(root, registry):
    if registry['schema_version'] != 1:
        raise ValueError('Unsupported experiment registry schema')
    specs = registry['experiments']
    ids = [e['experiment_id'] for e in specs]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate experiment ID: audits/repetitions cannot create duplicate rows')
    if registry['active_experiment_id'] not in ids:
        raise ValueError('Active experiment is not registered')
    rows = []
    for spec in specs:
        if spec['status'] not in STATUSES:
            raise ValueError('Unknown experiment status')
        if not (Path(root) / spec['evidence']).is_file():
            raise ValueError('Missing registered evidence: ' + spec['evidence'])
        if spec['status'] not in INCLUDED_STATUSES:
            continue
        if not spec.get('benchmark_record'):
            raise ValueError('Included experiment needs a normalized benchmark record')
        record = read_json(root, spec['benchmark_record'])
        if record.get('benchmark_schema_version') != 1:
            raise ValueError('Unsupported benchmark record schema')
        rows.append(experiment_row(spec, record, read_json(root, spec['evidence'])))
    if registry['active_experiment_id'] not in [r['experiment_id'] for r in rows]:
        raise ValueError('Active experiment must be completed/current')
    return rows


def number(value, digits=3):
    return 'Not recorded' if value is None else f'{value:,.{digits}f}'


def text(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def markdown(root, registry, rows, report_path, csv_path, registry_path='experiments/registry.json'):
    root, parent = Path(root).resolve(), Path(report_path).resolve().parent
    def link(path, label):
        return f'[{text(label)}]({os.path.relpath(root / path, parent)})'
    lines = ['# Results overview', '',
             '**Start here.** These tables read saved measurements; generating them runs no model or video processing.', '',
             'The thesis compares retrieval quality versus actual persistent index bytes, with construction time, search latency and memory as additional tradeoffs.', '',
             link(csv_path, 'Download/open the complete CSV') + ' · ' + link(registry_path, 'Experiment registry') + ' · ' + link('docs/BENCHMARKING.md', 'Measurement definitions'), '',
             '## Current experiment comparison', '',
             'One row per completed experiment. Audit records are views of a run, not new experiments. Superseded and failed runs remain below as history.', '',
             '| Method | Camera | Index bytes | Index build median (s; n) | Fresh query median (s; n) | Warm query median (ms; n) | Query Hit@5 |',
             '| --- | --- | ---: | --- | --- | --- | --- |']
    catalog_path = root / 'configs/experiments.json'
    if catalog_path.is_file():
        from .experiments import load_catalog, status
        setup = ['', '## Experiment setup: what to run', '',
                 link('configs/experiments.json', 'Edit the experiment catalog') +
                 '. Each entry specifies a method, footage, manifest, selection budget and query file. Planned rows have no measured results.', '',
                 '| Experiment ID | Method | Footage path | Selection settings | Status |',
                 '| --- | --- | --- | ---: | --- |']
        for spec in load_catalog(root)['experiments']:
            settings=f"{spec['interval_seconds']} s interval" if spec['method']=='uniform' else f"{spec['max_frames']} retained frames"
            setup.append(f'| `{spec["experiment_id"]}` | {spec["method"]} + OpenCLIP | {link(spec["footage"],spec["footage"])} | {settings} | {status(root,spec)} |')
        setup += ['', '```bash', '.venv/bin/python scripts/run_experiment.py list',
                  '.venv/bin/python scripts/run_experiment.py show --id uniform_5s_broadway43_dev_r01',
                  '.venv/bin/python scripts/run_experiment.py run --id uniform_5s_broadway43_dev_r01 --dry-run',
                  '# Remove --dry-run to execute this entry and add its verified measurements.', '```', '',
                  'A run uses new folders named after its experiment ID for the index, retrieval results and evidence. Existing runs cannot be overwritten; give repeats new IDs. Uniform and diversity sampling are supported. Comparing methods later requires the same footage and queries.', '']
        position = lines.index('## Current experiment comparison')
        lines[position:position] = setup
    for row in rows:
        hit = 'Pending annotations' if row['query_hit_at_5'] is None else f'{row["query_hit_at_5"]:.1%} ({row["quality_evaluated_queries"]} queries)'
        warm = row['warm_query_without_previews_median_s']
        lines.append(f'| {text(row["label"])} | {text(row["camera_id"])} | {number(row["index_bytes"],0)} | {number(row["indexing_median_s"])}; n={row["indexing_n"]} | {number(row["fresh_query_with_previews_median_s"])}; n={row["fresh_query_with_previews_n"]} | {number(None if warm is None else warm*1000)}; n={row["warm_query_without_previews_n"]} | {hit} |')
    quality_note = ('Accuracy is available only for rows with annotated queries.'
                    if any(row['query_hit_at_5'] is not None for row in rows)
                    else 'No retrieval accuracy has been measured.')
    lines += ['', '**Timing boundaries:** fresh queries include model startup, previews and result writes; warm queries use a resident model and exclude previews. They measure different scopes. One index build cannot establish variability. p95 is withheld below the protocol sample threshold. ' + quality_note, '', '## Prepared development clips', '',
              'All three use the same requested original-source window, 00:05:00–00:15:00. Sparse VFR timing yields 598.760 s of playable video. Use the saved timeline CSVs for precise source mapping.', '',
              '| Camera / video | Duration (s) | Resolution | Stored frames | Stored FPS | Visible-change Hz | Current comparison |',
              '| --- | ---: | --- | ---: | ---: | ---: | --- |']
    rates = read_json(root, registry['update_rates']) if registry.get('update_rates') else {}
    for spec in registry.get('datasets', []):
        dataset = read_json(root, spec['manifest'])
        if dataset['camera_id'] != spec['camera_id']:
            raise ValueError('Dataset registry camera does not match manifest')
        video = dataset['video']; meta = video['metadata']
        path = str(Path(spec['manifest']).parent / Path(video['path']).name)
        stream = meta.get('ffprobe', {}).get('streams', [{}])[0]
        fps = meta.get('avg_frame_rate')
        indexed = any(row['camera_id'] == spec['camera_id'] and row['video_sha256'] == video['sha256'] for row in rows)
        rate = rates.get('cameras', {}).get(spec['camera_id'], {}).get(registry.get('update_rate_scope'), {}).get('observable_change_hz')
        lines.append(f'| {link(path,dataset.get("camera_description",spec["camera_id"]))} | {number(meta.get("video_duration_seconds"))} | {meta["width"]}×{meta["height"]} | {stream.get("nb_frames","Not recorded")} | {number(float(Fraction(fps)) if fps else None,6)} | {number(rate,6)} | {"Indexed and verified" if indexed else "Prepared; no current index benchmark"} |')
    lines += ['', 'Visible-change rates come from the saved 80×48 grayscale analysis for this source window. They are content-change proxies, not network/sensor FPS. Video/index/preview binaries remain local and are excluded from Git.', '', '## Detailed experiment scorecards', '']
    for row in rows:
        lines += [f'### {text(row["experiment_id"])}', '',
                  link(row['record_path'], 'Normalized measurements') + ' · ' + link(row['evidence_path'], 'Raw run evidence'), '',
                  '| Category | Metric | Recorded value | Scope / limitation |', '| --- | --- | --- | --- |']
        def metric(category, name, value, scope):
            lines.append(f'| {category} | {name} | {text(value)} | {text(scope)} |')
        metric('Retrieval quality', 'Query Hit@5', 'Pending annotations' if row['query_hit_at_5'] is None else f'{row["query_hit_at_5"]:.1%}', row['quality_reason'] or 'Ground-truth query intervals required')
        metric('Representation', 'Retained items / embedding dimensions', f'{row["indexed_item_count"]} {row["indexed_item_kind"]} / {row["embedding_dimensions"]}', row['sampling_parameters_json'])
        metric('Construction', 'Candidate frames encoded', number(row['candidate_frames_encoded'],0), 'All candidate inference counts toward indexing, even if only a subset is retained')
        metric('Representation', 'Model / checkpoint', f'{row["model"]} / {row["checkpoint"]}', row['representation'])
        metric('Representation', 'Caption lengths', 'Not applicable' if json.loads(row['caption_lengths_json']).get('status') == 'not_applicable' else row['caption_lengths_json'], 'No captions stored by the current baseline')
        metric('Storage', 'Persistent retrieval index', f'{number(row["index_bytes"],0)} bytes', 'Actual retrieval-required files, including embedded metadata; excludes corpus and shared model files')
        for role, value in json.loads(row['storage_breakdown_json']).items():
            if role != 'retrieval_required':
                metric('Storage', role.replace('_',' '), 'Not inventoried' if value is None else f'{value:,} bytes', 'Separate from primary index budget')
        metric('Construction', 'End-to-end build', f'{number(row["indexing_median_s"])} s (n={row["indexing_n"]})', 'Fresh process; includes imports/model loading and full core build')
        metric('Construction', 'Model loading / core build', f'{number(row["model_loading_s"])} s / {number(row["core_build_s"])} s', 'Saved coarse timings; excludes imports from these two components')
        metric('Construction', 'Throughput', f'{number(row["throughput_input_video_hours_per_wall_hour"])} input-video hours/wall hour', 'Uses actual cropped-input duration; one observation, not an extrapolation to five hours')
        metric('Construction', 'Detailed stages', row['stages_status'], row['stages_reason'] or row['stage_timings_json'])
        for prefix, title, unit, scale in [('fresh_query_with_previews','Fresh-process queries','s',1),('warm_query_without_previews','Resident-model queries','ms',1000)]:
            value=row[prefix+'_median_s']; lo=row[prefix+'_minimum_s']; hi=row[prefix+'_maximum_s']; std=row[prefix+'_sample_stddev_s']
            metric('Search', title, f'{number(None if value is None else value*scale)} {unit} median; n={row[prefix+"_n"]}', 'With previews/startup' if scale==1 else 'No previews or model load; NPZ reloaded per query')
            metric('Search', title+' variability', f'{number(None if lo is None else lo*scale)}–{number(None if hi is None else hi*scale)} {unit}; sample SD {number(None if std is None else std*scale)} {unit}', 'Saved query workload; per-query details remain in the normalized record')
            metric('Search', title+' p95', 'Not recorded' if row[prefix+'_p95_s'] is None else number(row[prefix+'_p95_s']*scale)+' '+unit, row[prefix+'_p95_reason'])
        metric('Resources', 'Peak indexing process RAM', f'{number(row["indexing_peak_process_ram_bytes"],0)} bytes', row['memory_scope'])
        metric('Resources', 'Maximum query process RAM', f'{number(row["query_peak_process_ram_max_bytes"],0)} bytes', 'Maximum of recorded fresh-query worker lifetime peaks')
        metric('Resources', 'Accelerator peak memory', number(row['accelerator_peak_memory_bytes'],0), row['accelerator_peak_memory_reason'])
        metric('Resources', 'System-wide peak RAM', number(row['system_peak_ram_bytes'],0), row['system_peak_ram_reason'])
        metric('Environment', 'CPU model', row['cpu_model'] if row['cpu_model'] is not None else 'Not recorded', row['cpu_model_reason'])
        metric('Environment', 'Physical RAM capacity', number(row['physical_ram_bytes'],0), row['physical_ram_reason'])
        metric('Environment', 'Device / threads / seed', f'{row["device"]} / {row["threads"]} / {row["seed"]}', 'Recorded inference configuration')
        metric('Environment', 'Software versions', row['software_versions_json'], 'Recorded at original run time; current hardware is not backfilled')
        metric('Provenance', 'Video / availability', f'{row["camera_id"]}; SHA-256 {row["video_sha256"]}', row['availability_protocol_json'])
    lines += ['', '## Experiment history', '', '| Experiment | Status | Summary row? | Notes / evidence |', '| --- | --- | --- | --- |']
    for spec in registry['experiments']:
        lines.append(f'| {text(spec["experiment_id"])} | {spec["status"]} | {"Yes" if spec["status"] in INCLUDED_STATUSES else "No"} | {text(spec["notes"])} {link(spec["evidence"],"Evidence")} |')
    lines += ['', '## Refresh or extend this table', '', '```bash', '.venv/bin/python scripts/summarize_experiments.py', '```', '',
              'This regenerates only `experiments/summary.csv` and this overview from the registry and saved JSON. It does not rerun experiments or alter raw evidence. CSV empty cells mean unavailable/not applicable; status/reason columns preserve the distinction. Seconds and bytes are explicit in column names.', '',
              'For a new completed experiment, add its unique ID, status, evidence path and normalized `benchmark_record.json` to `experiments/registry.json`, then refresh. Mark superseded/failed attempts explicitly. Register one experiment once; never add its audit or each query repeat as another experiment. Unknown metrics remain empty with reasons.', '',
              'Next work: annotate fixed query/event intervals, gather repeated build and query measurements, then compare configurations under shared storage definitions. The current table organizes existing evidence; it does not add accuracy results or claim one method is cheaper.']
    return '\n'.join(lines)+'\n'


def generate(root, registry_path='experiments/registry.json', csv_path='experiments/summary.csv', report_path='docs/RESULTS_OVERVIEW.md'):
    root = Path(root).resolve()
    registry = read_json(root, registry_path)
    rows = collect(root, registry)
    # Build/validate both outputs before replacing these explicitly generated views.
    report = markdown(root, registry, rows, root / report_path, csv_path, registry_path)
    csv_target, md_target = root / csv_path, root / report_path
    if csv_target.suffix != '.csv' or md_target.suffix != '.md':
        raise ValueError('Generated outputs must use .csv and .md paths; research JSON must remain unchanged')
    input_paths = {str((root / spec['evidence']).resolve()) for spec in registry['experiments']}
    input_paths.add(str((root / registry_path).resolve()))
    input_paths.update(str((root / spec['benchmark_record']).resolve())
                       for spec in registry['experiments'] if spec.get('benchmark_record'))
    if any(str(path.resolve()) in input_paths for path in (csv_target, md_target)):
        raise ValueError('Generated outputs cannot replace experiment evidence')
    csv_target.parent.mkdir(parents=True, exist_ok=True); md_target.parent.mkdir(parents=True, exist_ok=True)
    with csv_target.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    md_target.write_text(report)
    return rows


def terminal_table(rows):
    """Compact saved-measurement comparison; unavailable values stay explicit."""
    header = ['Experiment', 'Method', 'Frames', 'Index bytes', 'Build s (n)',
              'Fresh s (n)', 'Warm ms (n)', 'Hit@5']
    table = [header]
    for row in rows:
        def latency(prefix, scale=1):
            value = row[prefix + '_median_s']
            return f'{number(None if value is None else value*scale)} ({row[prefix+"_n"]})'
        table.append([row['experiment_id'], row['sampling_method'],
                      str(row['indexed_item_count']), number(row['index_bytes'], 0),
                      latency('indexing'), latency('fresh_query_with_previews'),
                      latency('warm_query_without_previews', 1000),
                      'Pending' if row['query_hit_at_5'] is None else f'{row["query_hit_at_5"]:.1%}'])
    widths = [max(len(str(line[i])) for line in table) for i in range(len(header))]
    lines = [' | '.join(str(cell).ljust(width) for cell, width in zip(line, widths))
             for line in table]
    lines.insert(1, '-+-'.join('-'*width for width in widths))
    lines += ['', 'Saved measurements; n = timing observations, not independent videos.',
              'Fresh queries include startup/previews; warm queries exclude them.',
              'Frame-count matching is not exact byte matching. Accuracy requires event annotations.']
    return '\n'.join(lines)


def terminal_results(root, experiment_id):
    """Replay saved stats and ranked query results without inference or decoding."""
    registry = read_json(root, 'experiments/registry.json')
    spec = next((s for s in registry['experiments'] if s['experiment_id'] == experiment_id), None)
    if spec is None or not spec.get('benchmark_record'):
        raise ValueError(f'No completed measurements for {experiment_id}; planned entries must be run first')
    record = read_json(root, spec['benchmark_record'])
    evidence = read_json(root, spec['evidence'])
    row = experiment_row(spec, record, evidence)
    lines = [terminal_table([row]), '', 'Footage: ' + str(row['video_path']),
             f'Model: {row["model"]} / {row["checkpoint"]}; {row["embedding_dimensions"]} dimensions, {row["dtype"]}',
             'Candidate frames encoded: ' + number(row['candidate_frames_encoded'], 0),
             'Peak indexing process RAM: ' + number(row['indexing_peak_process_ram_bytes'], 0) + ' bytes',
             'Verification: PASS (pipeline checks; retrieval accuracy is separate)',
             'Evidence: ' + spec['evidence']]
    for i, result in enumerate(evidence.get('retrieval_results', []), 1):
        lines += ['', f'Query {i}: {result["query"]}',
                  'Rank | Clip timestamp | Source seconds | Cosine score | Preview filename']
        for match in result['results']:
            source = match.get('source_seconds')
            lines.append(f'{match["rank"]:>4} | {match.get("timestamp", number(match["seconds"]))} | '
                         f'{number(source)} | {match["cosine_similarity"]:.6f} | {match.get("image") or "No preview"}')
    lines += ['', 'Reading saved results only; no indexing or queries were rerun.',
              'Cosine scores are similarities, not probabilities or accuracy.']
    return '\n'.join(lines)
