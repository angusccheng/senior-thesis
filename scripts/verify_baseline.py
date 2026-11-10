"""Reproducible real-model audit. Run from the repository root with cached weights.

Creates a new artifact directory, executes the CLI in fresh processes, and writes
machine-readable evidence. This verifies mechanics, not semantic retrieval quality.
"""
import argparse
import io
import json
import os
from pathlib import Path
import shlex
import statistics
import struct
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
QUERIES = [
    'cars driving on a road beside trees',
    'a park with green trees and a walking path',
    'a person cooking food in a kitchen',
]


def mp4_timing(path):
    """Read ISO BMFF video-track timing tables without OpenCV or seeking.

    Intentionally small diagnostic parser for the ordinary, nonfragmented sample
    MP4, not a replacement for a general-purpose demuxer.
    """
    data = Path(path).read_bytes()

    def boxes(start, end):
        while start + 8 <= end:
            size, kind = struct.unpack_from('>I4s', data, start)
            header = 8
            if size == 1:
                size = struct.unpack_from('>Q', data, start + 8)[0]
                header = 16
            elif size == 0:
                size = end - start
            if size < header or start + size > end:
                raise ValueError('Invalid MP4 box length')
            yield kind, start + header, start + size
            start += size

    def child(start, end, kind):
        return next((a, b) for k, a, b in boxes(start, end) if k == kind)

    def duration(start):
        version = data[start]
        offset = start + (20 if version == 1 else 12)
        scale = struct.unpack_from('>I', data, offset)[0]
        ticks = struct.unpack_from('>Q' if version == 1 else '>I', data, offset + 4)[0]
        return scale, ticks

    moov = child(0, len(data), b'moov')
    movie_start, _ = child(*moov, b'mvhd')
    movie_scale, movie_ticks = duration(movie_start)
    for kind, start, end in boxes(*moov):
        if kind != b'trak':
            continue
        mdia = child(start, end, b'mdia')
        hdlr, _ = child(*mdia, b'hdlr')
        if data[hdlr + 8:hdlr + 12] != b'vide':
            continue
        mdhd, _ = child(*mdia, b'mdhd')
        scale, ticks = duration(mdhd)
        stbl = child(*child(*mdia, b'minf'), b'stbl')
        stts, _ = child(*stbl, b'stts')
        count = struct.unpack_from('>I', data, stts + 4)[0]
        runs = [struct.unpack_from('>II', data, stts + 8 + i * 8) for i in range(count)]
        return {'video_timescale': scale, 'video_duration_ticks': ticks,
                'video_duration_seconds': ticks / scale,
                'movie_duration_seconds': movie_ticks / movie_scale,
                'sample_count': sum(n for n, _ in runs),
                'time_to_sample_runs': runs,
                'constant_frame_rate': len({delta for _, delta in runs}) == 1,
                'fps': scale / runs[0][1] if len({delta for _, delta in runs}) == 1 else None}
    raise ValueError('No video timing table found')


def guarded_search(arguments):
    """Fresh-process proof that index-only search never decodes/embeds images."""
    from video_search.encoder import OpenCLIPEncoder
    import main
    sys.argv = ['main.py', *arguments]
    with patch.object(OpenCLIPEncoder, 'encode_images', side_effect=AssertionError('Image re-encoding during search')), \
         patch('video_search.video.decode_video', side_effect=AssertionError('Source decoding during index-only search')), \
         patch.object(main, 'build_index', side_effect=AssertionError('Index rebuilt during search')):
        main.main()


def verify(output):
    os.environ['HF_HUB_OFFLINE'] = '1'
    import cv2
    import numpy as np
    from PIL import Image
    from video_search.encoder import OpenCLIPEncoder
    from video_search.pipeline import load_index, search_index, sha256_file, environment

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, 'HF_HUB_OFFLINE': '1'}
    commands, checks = [], []
    evidence = {'commands': commands, 'checks': checks, 'queries': QUERIES}

    def save():
        (output / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')

    def check(name, condition, **details):
        checks.append({'name': name, 'passed': bool(condition), **details})
        save()
        if not condition:
            raise AssertionError(name)
        print(f'PASS: {name}', flush=True)

    def run(arguments, expected=0):
        command = [sys.executable, *map(str, arguments)]
        started = perf_counter()
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        elapsed = perf_counter() - started
        record = {'command': 'HF_HUB_OFFLINE=1 ' + shlex.join(command),
                  'returncode': result.returncode, 'expected_returncode': expected,
                  'wall_seconds': elapsed, 'stdout': result.stdout, 'stderr': result.stderr}
        commands.append(record)
        save()
        if result.returncode != expected:
            raise AssertionError(record)
        return record

    run(['-m', 'unittest', 'discover', '-s', 'tests', '-v'])
    check('Offline regression suite', True)
    run(['-m', 'pip', 'check'])
    check('Installed dependency consistency', True)
    video = Path('data/sample.mp4')
    timing = mp4_timing(video)
    evidence['independent_mp4_timing'] = timing
    check('Independent MP4 timing table is CFR', timing['constant_frame_rate'])
    index = output / 'index.npz'
    indexing = run(['main.py', 'index', '--video', video, '--interval', '1',
                    '--batch-size', '4', '--threads', '4', '--index', index])
    e, timestamps, numbers, meta = load_index(index)
    evidence['index_metadata'] = meta
    evidence['environment'] = environment()
    evidence['source_sha256'] = sha256_file(video)
    evidence['index_sha256'] = sha256_file(index)
    initial_index_hash = evidence['index_sha256']
    check('Video duration/FPS agrees with MP4 timing tables',
          abs(meta['source']['duration_seconds'] - timing['video_duration_seconds']) < 1e-9
          and abs(meta['source']['fps'] - timing['fps']) < 1e-9)

    # Independent CFR expectation, derived from MP4 stts, not UniformSampler.
    targets = np.arange(0, timing['video_duration_seconds'], 1.)
    expected_numbers = np.unique(np.ceil(targets * timing['fps'] - 1e-9).astype(np.int64))
    expected_numbers = expected_numbers[expected_numbers < timing['sample_count']]
    check('Expected uniform sample count and frame numbers', np.array_equal(numbers, expected_numbers),
          expected_count=len(expected_numbers), actual_count=len(numbers), frame_numbers=numbers.tolist())
    check('Stored timestamps match independent CFR frame times',
          np.allclose(timestamps, numbers / timing['fps'], atol=1e-9, rtol=0), seconds=timestamps.tolist())
    check('Embedding shape, dtype, finite values and normalization',
          e.shape == (len(numbers), 512) and e.dtype == np.float32 and np.isfinite(e).all()
          and np.allclose(np.linalg.norm(e, axis=1), 1, atol=1e-6),
          shape=list(e.shape), maximum_norm_error=float(np.max(np.abs(np.linalg.norm(e, axis=1) - 1))))
    # A second standalone load must reproduce arrays without invoking an encoder.
    again = load_index(index)
    check('Disk round trip preserves all numeric arrays', all(np.array_equal(x, y) for x, y in zip((e, timestamps, numbers), again[:3])))

    results, query_times = [], []
    for i, query in enumerate(QUERIES, 1):
        folder = output / f'query_{i:02d}'
        command = run(['main.py', 'search', '--index', index, '--query', query,
                       '--top-k', '5', '--output', folder])
        query_times.append(command['wall_seconds'])
        result = json.loads((folder / 'results.json').read_text())
        results.append(result)
        repeated_folder = output / f'query_{i:02d}_repeat'
        run(['main.py', 'search', '--index', index, '--query', query,
             '--top-k', '5', '--output', repeated_folder])
        repeated = json.loads((repeated_folder / 'results.json').read_text())
        check(f'Query {i}: five results, sorted scores, fresh-process repeat equality',
              len(result['results']) == 5 and result['results'] == repeated['results']
              and all(a['cosine_similarity'] >= b['cosine_similarity']
                      for a, b in zip(result['results'], result['results'][1:])))
    evidence['retrieval_results'] = results
    run(['scripts/verify_baseline.py', '--guarded-search', 'search', '--index', index,
         '--query', QUERIES[0], '--no-previews', '--output', output / 'index_only_guard'])
    check('Fresh index-only search neither rebuilds index nor embeds/decodes images', True)

    # Decode independently of production video.py, then re-encode all retained
    # images to establish that each stored vector belongs to its saved timestamp.
    cap = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG)
    frames, all_times, number = {}, [], 0
    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            seconds = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            all_times.append(seconds)
            if number in numbers:
                frames[number] = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            number += 1
    finally:
        cap.release()
    check('Every decoded timestamp agrees with independent CFR timing',
          number == timing['sample_count'] and np.allclose(all_times, np.arange(number) / timing['fps'], atol=1e-9))
    encoder = OpenCLIPEncoder(device='cpu', threads=4)
    recomputed = []
    for start in range(0, len(numbers), 4):
        recomputed.append(encoder.encode_images([frames[int(n)] for n in numbers[start:start + 4]]))
    recomputed = np.concatenate(recomputed)
    check('Every embedding maps to its source frame and timestamp',
          np.allclose(e, recomputed, atol=1e-6, rtol=1e-5),
          max_embedding_difference=float(np.max(np.abs(e - recomputed))))
    max_cosine_error = 0.
    for i, result in enumerate(results, 1):
        q = encoder.encode_text(result['query']).astype(np.float64)
        # Independent explicit cosine formula, with both norms retained.
        stored = e.astype(np.float64)
        cosine = np.sum(stored * q[None, :], axis=1) / (np.linalg.norm(stored, axis=1) * np.linalg.norm(q))
        order = sorted(range(len(numbers)), key=lambda j: (-cosine[j], j))[:5]
        rows = result['results']
        check(f'Query {i}: independent cosine calculation and top-five ordering',
              [r['frame_number'] for r in rows] == [int(numbers[j]) for j in order]
              and all(abs(row['cosine_similarity'] - cosine[j]) < 1e-6 for row, j in zip(rows, order)))
        for row, j in zip(rows, order):
            max_cosine_error = max(max_cosine_error, abs(row['cosine_similarity'] - cosine[j]))
            check(f"Query {i}, rank {row['rank']}: timestamp and exact saved JPEG",
                  row['seconds'] == float(timestamps[j]) and row['frame_number'] == int(numbers[j])
                  and row['timestamp'] == f"00:00:{int(timestamps[j]):02d}.000"
                  and row['image'] == f"rank_{row['rank']:02d}_frame_{int(numbers[j]):08d}.jpg")
            buffer = io.BytesIO()
            frames[row['frame_number']].save(buffer, format='JPEG', quality=95)
            expected_bytes = buffer.getvalue()
            for suffix in ('', '_repeat'):
                image = output / f'query_{i:02d}{suffix}' / row['image']
                check(f"Query {i}{suffix}, rank {row['rank']}: JPEG matches decoded source frame",
                      image.read_bytes() == expected_bytes, image=str(image))

    # Resident-model times include load_index, compatibility checks, text encoding,
    # ranking, and result-row construction; exclude model load and preview export.
    encoder.metadata()  # Exclude one-time model fingerprint from resident timing.
    search_index(index, QUERIES[0], encoder)  # One explicitly untimed warm-up.
    resident = []
    for _ in range(3):
        for query in QUERIES:
            started = perf_counter()
            search_index(index, query, encoder)
            resident.append(perf_counter() - started)
    invalid_video = run(['main.py', 'index', '--video', output / 'missing.mp4',
                         '--index', output / 'invalid.npz'], expected=2)
    empty_query = run(['main.py', 'search', '--index', index, '--query', '   ',
                       '--output', output / 'empty_query'], expected=2)
    check('Invalid video path and empty query exit cleanly without traceback',
          all('Error:' in record['stderr'] and 'Traceback' not in record['stderr']
              for record in (invalid_video, empty_query)))
    check('Searches leave saved index unchanged', sha256_file(index) == initial_index_hash)
    evidence['performance'] = {
        'indexing_fresh_process_seconds': indexing['wall_seconds'],
        'query_fresh_process_seconds': query_times,
        'average_query_fresh_process_seconds': statistics.mean(query_times),
        'query_resident_seconds': resident,
        'average_query_resident_seconds': statistics.mean(resident),
        'resident_timed_queries': len(resident), 'resident_untimed_warmups': 1,
        'index_file_bytes': index.stat().st_size,
        'numeric_payload_bytes': meta['storage']['payload_bytes'],
        'maximum_independent_cosine_error': max_cosine_error,
        'conditions': 'CPU, 4 Torch threads, fp32, seed 0, batch size 4, 1 s interval, cached weights; no downloads. Fresh process times include interpreter/import/model load and preview/results I/O. Resident timings exclude model load, initial fingerprint and previews, but reload NPZ per query. Single indexing measurement; three fresh-process queries; nine resident queries.'}
    evidence['passed'] = all(c['passed'] for c in checks)
    save()
    print(json.dumps(evidence['performance'], indent=2), flush=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--guarded-search':
        guarded_search(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='output/verification_2026-10-27')
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT:
        parser.error('Run this script from the repository root')
    verify(args.output)


if __name__ == '__main__':
    main()
