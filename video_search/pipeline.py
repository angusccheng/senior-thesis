"""Index construction and exact retrieval, independent of the sampling policy."""
import hashlib
import importlib.metadata
import json
import os
import platform
import tempfile
from time import perf_counter
from pathlib import Path

import numpy as np
from PIL import Image

from .samplers import Sampler
from .video import FrameInfo, scan_video, selected_frames, video_properties
from .dataset import DatasetContext
from .benchmarking import StageTimings, peak_process_ram

SCHEMA_VERSION = 1
PACKAGES = ('numpy', 'opencv-python', 'Pillow', 'torch', 'torchvision', 'open_clip_torch', 'timm')


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def environment():
    return {'python': platform.python_version(), 'platform': platform.platform(),
            'packages': {p: importlib.metadata.version(p) for p in PACKAGES}}


def build_index(video, sampler: Sampler, encoder, output, batch_size=16, dataset_manifest=None):
    started = perf_counter()
    stages = StageTimings()
    if batch_size <= 0:
        raise ValueError('batch_size must be positive')
    output, video = Path(output), Path(video).resolve()
    if output.exists():
        raise FileExistsError(f'Choose a new index path; already exists: {output}')
    source_hash = stages.call('input_fingerprint', sha256_file, video)
    dataset = stages.call('dataset_validation', DatasetContext, dataset_manifest, video, source_hash) if dataset_manifest else None
    properties = stages.call('video_probe', video_properties, video)
    frames = stages.call('timeline_decoding', scan_video, video)
    chosen = stages.call('selection', sampler.select, frames)
    candidates_before_eligibility = len(chosen)
    if dataset is not None:
        with stages.measure('eligibility_filter'):
            chosen = [frame for frame in chosen if dataset.eligible(frame)]
    encoded_candidates = len(chosen)
    if not chosen:
        raise ValueError('No eligible sampled frames; check sampling and dataset availability')
    if len({f.number for f in chosen}) != len(chosen) or chosen != sorted(chosen, key=lambda f: f.number):
        raise ValueError('Sampler must return unique frames in chronological order')
    if any(f.number < 0 or f.number >= len(frames) or frames[f.number] != f for f in chosen):
        raise ValueError('Sampler returned frames outside the source timeline')
    batches, images = [], []
    for _, rgb in stages.iterate('selected_frame_decoding', selected_frames(video, chosen)):
        with stages.measure('rgb_to_pil'):
            images.append(Image.fromarray(rgb))
        if len(images) == batch_size:
            batches.append(stages.call('image_encoding_including_preprocess', encoder.encode_images, images))
            images = []
    if images:
        batches.append(stages.call('image_encoding_including_preprocess', encoder.encode_images, images))
    if stages.call('source_integrity_recheck', sha256_file, video) != source_hash:
        raise ValueError('Source video changed during indexing')
    embeddings = np.concatenate(batches).astype(np.float32)
    # Validate every candidate before selection so discarded invalid features
    # cannot hide encoder failures. No candidate images are retained in RAM.
    validate_arrays(embeddings, np.array([f.seconds for f in chosen]),
                    np.array([f.number for f in chosen], dtype=np.int64))
    feature_selection = getattr(sampler, 'select_embeddings', None)
    if feature_selection is not None:
        positions = stages.call('diversity_selection', feature_selection, embeddings)
        if (positions.ndim != 1 or positions.dtype != np.int64 or not len(positions)
                or np.any(positions < 0) or np.any(positions >= len(chosen))
                or np.any(np.diff(positions) <= 0)):
            raise ValueError('Feature sampler must return increasing unique candidate positions')
        chosen = [chosen[i] for i in positions]
        embeddings = embeddings[positions]
    with stages.measure('index_arrays_and_validation'):
        timestamps = np.array([f.seconds for f in chosen], dtype=np.float64)
        frame_numbers = np.array([f.number for f in chosen], dtype=np.int64)
        source_timestamps = dataset.timestamps(chosen) if dataset is not None else None
        validate_arrays(embeddings, timestamps, frame_numbers)
    if len(embeddings) != len(chosen):
        raise ValueError('Encoder returned an incorrect batch size')
    metadata = {
        'schema_version': SCHEMA_VERSION,
        'source': {'path': str(video), 'sha256': source_hash,
                   **properties,
                   'bytes': video.stat().st_size, 'decoded_frames': len(frames),
                   'last_frame_seconds': frames[-1].seconds,
                   'timestamps': 'OpenCV FFmpeg CAP_PROP_POS_MSEC; seconds'},
        'sampler': sampler.metadata(), 'encoder': stages.call('model_fingerprint', encoder.metadata),
        'preprocess': str(encoder.preprocess), 'environment': environment(),
        'batch_size': batch_size, 'frames': len(chosen),
        'candidate_frames_encoded': encoded_candidates,
        'embedding_dimension': embeddings.shape[1],
        'embedding_dtype': str(embeddings.dtype),
        'storage': {'embedding_bytes': embeddings.nbytes,
                    'timestamp_bytes': timestamps.nbytes,
                    'frame_number_bytes': frame_numbers.nbytes,
                    'payload_bytes': embeddings.nbytes + timestamps.nbytes + frame_numbers.nbytes,
                    'format': 'uncompressed NPZ; embedded JSON metadata'},
    }
    if dataset is not None:
        metadata['dataset'] = dataset.metadata
        metadata['eligibility'] = {
            'candidates_before_eligibility': candidates_before_eligibility,
            'excluded_candidates': candidates_before_eligibility - encoded_candidates,
            'rule': 'Apply shared source-time eligibility before image encoding and optional feature selection'}
        if sampler.metadata()['name'] == 'uniform':
            metadata['eligibility']['uniform_candidates'] = candidates_before_eligibility
        metadata['storage']['source_timestamp_bytes'] = source_timestamps.nbytes
        metadata['storage']['payload_bytes'] += source_timestamps.nbytes
    metadata['indexing_seconds_before_persistence'] = perf_counter() - started
    output.parent.mkdir(parents=True, exist_ok=True)
    # All authoritative data in one archive, replaced only after a complete write.
    temporary = None
    with stages.measure('index_persistence'):
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, suffix='.npz', delete=False) as stream:
                temporary = Path(stream.name)
                extra = {'source_timestamps': source_timestamps} if source_timestamps is not None else {}
                np.savez(stream, embeddings=embeddings, timestamps=timestamps,
                         frame_numbers=frame_numbers, metadata=np.array(json.dumps(metadata, sort_keys=True)), **extra)
            os.replace(temporary, output)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    index_hash = stages.call('output_fingerprint', sha256_file, output)
    elapsed = perf_counter() - started
    report = {**metadata, 'index_file_bytes': output.stat().st_size,
              'index_sha256': index_hash, 'indexing_seconds': elapsed,
              'benchmark_instrumentation_version': 1,
              'indexing_stage_timings': stages.snapshot(),
              'indexing_unattributed_seconds': max(0., elapsed - sum(stages.seconds.values())),
              'input_video_hours_per_wall_hour': properties['duration_seconds'] / elapsed if properties['duration_seconds'] is not None and elapsed > 0 else None,
              'indexing_peak_process_ram': peak_process_ram(),
              'timing_scope': 'build_index entry through NPZ persistence and output checksum; excludes model construction/imports and report serialization. Image encoding combines transforms, inference, normalization and device-to-CPU transfer. Synchronous CPU stages; array/provenance assembly and bookkeeping remain unattributed.'}
    output.with_suffix('.metadata.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def validate_arrays(embeddings, timestamps, frame_numbers):
    n = len(embeddings)
    if embeddings.ndim != 2 or n == 0 or embeddings.shape[1] == 0 or embeddings.dtype != np.float32:
        raise ValueError('Index needs a nonempty float32 embedding matrix')
    if timestamps.shape != (n,) or frame_numbers.shape != (n,):
        raise ValueError('Index arrays have incompatible shapes')
    if not np.isfinite(embeddings).all() or not np.allclose(np.linalg.norm(embeddings, axis=1), 1, atol=1e-5):
        raise ValueError('Index embeddings must be finite unit vectors')
    if not np.isfinite(timestamps).all() or np.any(timestamps < 0) or np.any(np.diff(timestamps) <= 0):
        raise ValueError('Index timestamps must be finite, nonnegative and increasing')
    if frame_numbers.dtype != np.int64 or np.any(frame_numbers < 0) or np.any(np.diff(frame_numbers) <= 0):
        raise ValueError('Index frame numbers must be increasing int64 values')


def load_index(path):
    with np.load(path, allow_pickle=False) as archive:
        embeddings, timestamps = archive['embeddings'], archive['timestamps']
        numbers = archive['frame_numbers']
        metadata = json.loads(str(archive['metadata'].item()))
        if 'dataset' in metadata:
            original_times = archive['source_timestamps']
            if (original_times.shape != timestamps.shape or original_times.dtype != np.float64
                    or not np.isfinite(original_times).all() or np.any(original_times < 0)
                    or np.any(np.diff(original_times) <= 0)):
                raise ValueError('Invalid original-recording timestamps in index')
    if metadata['schema_version'] != SCHEMA_VERSION:
        raise ValueError('Unsupported index schema')
    validate_arrays(embeddings, timestamps, numbers)
    if metadata['frames'] != len(embeddings) or metadata['embedding_dimension'] != embeddings.shape[1]:
        raise ValueError('Index metadata does not match arrays')
    return embeddings, timestamps, numbers, metadata


def rank_frames(embeddings, query_embedding, top_k=5):
    if top_k <= 0:
        raise ValueError('top_k must be positive')
    query = np.asarray(query_embedding, dtype=np.float32)
    if query.shape != (embeddings.shape[1],) or not np.isfinite(query).all():
        raise ValueError('Invalid query embedding')
    if not np.isclose(np.linalg.norm(query), 1, atol=1e-5):
        raise ValueError('Query embedding must be a unit vector')
    scores = embeddings @ query
    # Stable sort resolves ties by chronological index order.
    winners = np.argsort(-scores, kind='stable')[:top_k]
    return winners, scores


def search_index(index, query, encoder, top_k=5):
    if not query.strip():
        raise ValueError('Query cannot be empty')
    embeddings, timestamps, numbers, metadata = load_index(index)
    actual = encoder.metadata()
    for key in ('model', 'pretrained', 'weights_sha256', 'precision'):
        if metadata['encoder'][key] != actual[key]:
            raise ValueError(f'Index and query encoder mismatch: {key}')
    # Changes to preprocessing or library versions also invalidate comparisons.
    current = environment()
    if current['packages'] != metadata['environment']['packages'] or str(encoder.preprocess) != metadata['preprocess']:
        raise ValueError('Encoder environment/preprocessing differs from index; use the recorded dependencies')
    winners, scores = rank_frames(embeddings, encoder.encode_text(query), top_k)
    rows = [{'rank': rank, 'frame_number': int(numbers[i]), 'seconds': float(timestamps[i]),
             'cosine_similarity': float(scores[i])} for rank, i in enumerate(winners, 1)]
    if 'dataset' in metadata:
        with np.load(index, allow_pickle=False) as archive:
            source_times = archive['source_timestamps']
        if source_times.shape != timestamps.shape or not np.isfinite(source_times).all():
            raise ValueError('Invalid source-timestamp array')
        for row, i in zip(rows, winners):
            row['source_seconds'] = float(source_times[i])
            row['camera_id'] = metadata['dataset']['camera_id']
    return rows, metadata


def export_previews(rows, metadata, output, video=None):
    source = Path(video or metadata['source']['path'])
    if sha256_file(source) != metadata['source']['sha256']:
        raise ValueError('Preview video does not match indexed source SHA-256')
    by_number = {row['frame_number']: row for row in rows}
    chosen = [FrameInfo(row['frame_number'], row['seconds']) for row in rows]
    for info, rgb in selected_frames(source, chosen):
        row = by_number[info.number]
        name = f"rank_{row['rank']:02d}_frame_{info.number:08d}.jpg"
        Image.fromarray(rgb).save(Path(output) / name, quality=95)
        row['image'] = name
