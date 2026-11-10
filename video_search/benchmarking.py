"""Small, representation-independent measurement helpers; no model dependencies."""
from contextlib import contextmanager
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter

BENCHMARK_SCHEMA_VERSION = 1
P95_MIN_SAMPLES = 100  # At least five observations in the nominal upper 5% tail.


def unavailable(reason):
    return {'status': 'unavailable', 'value': None, 'reason': reason}


def latency_summary(samples):
    """Seconds; retain raw observations and avoid unsupported tail/variance claims."""
    samples = [float(value) for value in samples]
    if any(not math.isfinite(value) or value < 0 for value in samples):
        raise ValueError('Timing samples must be finite, nonnegative seconds')
    if not samples:
        return {'unit': 'seconds', 'count': 0, 'samples': [], 'summary': unavailable('No measurements recorded')}
    result = {'unit': 'seconds', 'count': len(samples), 'samples': samples,
              'mean': statistics.mean(samples), 'median': statistics.median(samples),
              'minimum': min(samples), 'maximum': max(samples),
              'sample_stddev': statistics.stdev(samples) if len(samples) >= 2 else None,
              'stddev_reason': None if len(samples) >= 2 else 'A single measurement cannot estimate variability',
              'p95': None, 'p95_estimator': 'nearest-rank ceil(0.95*n)',
              'p95_min_samples': P95_MIN_SAMPLES}
    if len(samples) >= P95_MIN_SAMPLES:
        result['p95'] = sorted(samples)[math.ceil(.95 * len(samples))-1]
        result['p95_reason'] = None
    else:
        result['p95_reason'] = f'Fewer than {P95_MIN_SAMPLES} samples; tail estimate withheld by protocol'
    return result


class StageTimings:
    """Exclusive synchronous wall-clock stages. Nested stages are rejected."""
    def __init__(self, clock=perf_counter):
        self.clock, self.seconds, self.calls = clock, {}, {}
        self.active = None

    @contextmanager
    def measure(self, name):
        if self.active is not None:
            raise ValueError('Nested benchmark stages would double-count elapsed time')
        self.active = name
        began = self.clock()
        try:
            yield
        finally:
            self.seconds[name] = self.seconds.get(name, 0.) + self.clock() - began
            self.calls[name] = self.calls.get(name, 0) + 1
            self.active = None

    def call(self, name, function, *args, **kwargs):
        with self.measure(name):
            return function(*args, **kwargs)

    def iterate(self, name, iterable):
        """Time advancing the decoder, not the consumer's encoding/processing."""
        iterator = iter(iterable)
        try:
            while True:
                with self.measure(name):
                    try:
                        value = next(iterator)
                    except StopIteration:
                        return
                yield value
        finally:
            if hasattr(iterator, 'close'):
                iterator.close()

    def snapshot(self):
        return {name: {'seconds': value, 'calls': self.calls[name]} for name, value in self.seconds.items()}


def peak_process_ram():
    """Process-lifetime high-water RSS, never mislabeled as a warm-phase delta."""
    if sys.platform not in ('darwin', 'linux'):
        return unavailable('ru_maxrss units are not supported by this helper on this platform')
    try:
        import resource
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {'status': 'measured', 'value': int(raw if sys.platform == 'darwin' else raw * 1024),
                'unit': 'bytes', 'scope': 'current process lifetime; includes imports/model loading; excludes children/system-wide usage',
                'method': 'getrusage(RUSAGE_SELF).ru_maxrss; Darwin bytes / Linux KiB converted'}
    except (ImportError, OSError) as error:
        return unavailable(str(error))


def _sysctl(key):
    try:
        result = subprocess.run(['sysctl', '-n', key], capture_output=True, text=True, timeout=2)
        if result.returncode:
            return unavailable(result.stderr.strip() or 'sysctl failed')
        value = result.stdout.strip()
        return {'status': 'measured', 'value': value, 'method': f'sysctl -n {key}'} if value else unavailable('sysctl returned no value')
    except (OSError, subprocess.TimeoutExpired) as error:
        return unavailable(str(error))


def capture_hardware(inference_device='cpu'):
    """Capture now; never backfill historical hardware as if measured at run time."""
    result = {'os': platform.platform(), 'architecture': platform.machine(),
              'python': platform.python_version(), 'logical_cpu_count': os.cpu_count(),
              'inference_device': inference_device,
              'system_wide_memory_sampling': unavailable('Not collected; process RSS is a different measurement'),
              'accelerator_model': unavailable('No accelerator discovery performed'),
              'accelerator_peak_memory': unavailable('CPU run: no accelerator used' if inference_device == 'cpu' else 'No peak-memory provider configured for this device')}
    if sys.platform == 'darwin':
        result['cpu_model'] = _sysctl('machdep.cpu.brand_string')
        result['physical_ram_bytes'] = _sysctl('hw.memsize')
        if result['physical_ram_bytes']['status'] == 'measured':
            try:
                result['physical_ram_bytes']['value'] = int(result['physical_ram_bytes']['value'])
                result['physical_ram_bytes']['unit'] = 'bytes'
            except ValueError:
                result['physical_ram_bytes'] = unavailable('Unexpected hw.memsize format')
    elif sys.platform == 'linux':
        try:
            models = [line.partition(':')[2].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')]
            result['cpu_model'] = {'status': 'measured', 'value': models[0], 'method': '/proc/cpuinfo'} if models else unavailable('CPU model not exposed')
        except OSError as error:
            result['cpu_model'] = unavailable(str(error))
        try:
            result['physical_ram_bytes'] = {'status': 'measured', 'value': os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE'),
                                            'unit': 'bytes', 'scope': 'physical OS memory; container/process limits not measured'}
        except (OSError, ValueError) as error:
            result['physical_ram_bytes'] = unavailable(str(error))
    else:
        result['cpu_model'] = unavailable('No CPU-model provider for this platform')
        result['physical_ram_bytes'] = unavailable('No physical-RAM provider for this platform')
    return result


def storage_inventory(artifacts):
    """Count explicit files by role; only retrieval_required enters primary budget."""
    allowed = {'retrieval_required', 'original_video', 'processed_video', 'shared_model',
               'experiment_metadata', 'preview', 'temporary'}
    records, seen, totals = [], set(), {role: 0 for role in allowed}
    counts, missing = {role: 0 for role in allowed}, set()
    missing_required = False
    for artifact in artifacts:
        path, role = Path(artifact['path']), artifact['role']
        if role not in allowed:
            raise ValueError(f'Unknown storage role: {role}')
        resolved = str(path.resolve())
        if resolved in seen:
            raise ValueError('An artifact cannot be counted twice through different paths/roles')
        seen.add(resolved)
        counts[role] += 1
        entry = {**artifact, 'resolved_path': resolved}
        if path.is_file():
            entry.update(status='measured', bytes=path.stat().st_size)
            totals[role] += entry['bytes']
        else:
            entry.update(status='unavailable', bytes=None, reason='File absent or not a regular file')
            missing.add(role)
            missing_required |= role == 'retrieval_required'
        records.append(entry)
    complete = not missing_required and counts['retrieval_required'] > 0
    return {'files': records,
            'measured_bytes_by_role': {role: totals[role] if counts[role] and role not in missing else None for role in allowed},
            'listed_file_count_by_role': counts,
            'role_status': {role: 'not_inventoried' if not counts[role] else ('unavailable' if role in missing else 'measured') for role in allowed},
            'primary_index_bytes': totals['retrieval_required'] if complete else None,
            'primary_status': 'measured' if complete else 'unavailable',
            'definition': 'Actual per-dataset retrieval-required files; shared models, corpus videos, previews, benchmark reports and temporary artifacts reported separately'}


def baseline_record(data, index_path, evidence_path):
    """Adapter from the existing completed baseline run into the common cost schema.

    Other representations should emit the same top-level source/method/storage/
    timing/memory/environment fields using the measurement helpers above.
    This adapter never recreates missing measurements or loads a video/model.
    """
    meta, perf = data['index_metadata'], data['performance']
    searches = [c for c in data['commands'] if c.get('metrics', {}).get('retrieval_guards')]
    fresh = [c['wall_seconds'] for c in searches]
    resident = perf.get('resident_query_seconds', [])
    source = meta.get('dataset', {}).get('source_recording', {})
    files = [{'path': str(index_path), 'role': 'retrieval_required'},
             {'path': str(Path(index_path).with_suffix('.metadata.json')), 'role': 'experiment_metadata'},
             {'path': meta['source']['path'], 'role': 'processed_video'}]
    if source.get('path'):
        files.append({'path': source['path'], 'role': 'original_video'})
    return {
        'benchmark_schema_version': BENCHMARK_SCHEMA_VERSION,
        'experiment_id': Path(evidence_path).parent.name, 'evidence_path': str(evidence_path),
        'source': {'video': meta['source'], 'camera_id': meta.get('dataset', {}).get('camera_id'),
                   'dataset_id': meta.get('dataset', {}).get('dataset_id'),
                   'original_recording': source or None,
                   'valid_source_intervals': meta.get('dataset', {}).get('valid_source_intervals'),
                   'availability': meta.get('dataset', {}).get('availability_report')},
        'method': {'sampling': meta['sampler'], 'representation': 'OpenCLIP image/text embeddings',
                   'encoder': meta['encoder'], 'embedding_dimension': meta['embedding_dimension'],
                   'dtype': meta.get('embedding_dtype'), 'indexed_items': {'kind': 'frame', 'count': meta['frames']},
                   'inference_settings': {'batch_size': meta.get('batch_size'), 'preprocess': meta.get('preprocess')}},
        'repetitions': {'indexing': 1, 'fresh_process_per_query': 2, 'resident_per_query': 3,
                        'query_count': len(data['queries']), 'untimed_resident_warmups': 1},
        'storage': storage_inventory(files),
        'storage_unmeasured': {
            'shared_model_files': unavailable('Not inventoried; do not equate all cache files with required model storage'),
            'all_preview_and_temporary_bytes': unavailable('Not aggregated; neither is required by index-only retrieval')},
        'timing': {
            'indexing_end_to_end_seconds': latency_summary([perf['indexing_fresh_process_seconds']]),
            'indexing_stage_seconds': meta.get('indexing_stage_timings', unavailable('Stage timers were not present; cannot reconstruct stages retrospectively')),
            'source_video_hours_per_wall_hour': meta['source']['duration_seconds'] / perf['indexing_fresh_process_seconds'],
            'throughput_denominator': 'Actual input cropped-video duration, not whole original recording or requested clip-window duration',
            'fresh_process_query_with_previews_seconds': latency_summary(fresh),
            'resident_query_without_previews_seconds': latency_summary(resident),
            'pure_cold_query_without_preview_seconds': unavailable('Fresh-process measurement includes preview extraction and result I/O'),
            'per_query': {f'q{i+1}': {'text': query, 'fresh_process_seconds': latency_summary(fresh[2*i:2*i+2]),
                                     'resident_seconds': latency_summary(resident[i::len(data['queries'])])}
                          for i, query in enumerate(data['queries'])}},
        'memory': {'scope': 'Process-specific lifetime high-water RSS; excludes child/system memory. Not a warm-query-only allocation delta.',
                   'index_peak_process_ram_bytes': perf['index_peak_rss_bytes'],
                   'fresh_query_peak_process_ram_bytes': perf['query_peak_rss_bytes'],
                   'system_wide_peak_ram': unavailable('Not recorded'),
                   'accelerator_peak_memory': unavailable('CPU run; no accelerator peak recorded')},
        'environment': {'software_at_run': meta['environment'],
                        'hardware_at_run': data.get('hardware_at_run_start', unavailable('CPU model/RAM capacity not recorded at original-run time'))},
        'ground_truth_accuracy': unavailable('No annotated event intervals; qualitative examples do not establish accuracy'),
        'measurement_boundaries': {
            'indexing': 'Fresh process: interpreter/imports, model loading, decoding, selection, inference, validation, persistence and metadata output.',
            'common_dataset_preparation': 'Input is an already prepared clip and availability protocol. Shared cropping/availability costs are separate, not silently charged to only one strategy.',
            'strategy_required_preprocessing': 'Must occur inside total strategy timing, including full-video selection scans or feature precomputation.',
            'fresh_process_queries': 'Includes model loading, NPZ/validation, text encoding, ranking, cropped-video previews and result I/O; OS caches not cleared.',
            'resident_queries': 'Resident model/cached fingerprint; one untimed warm-up; 3 rounds of 3 queries; NPZ reloaded; no previews.'}}
