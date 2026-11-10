"""FFmpeg dataset preparation, separate from the OpenCLIP retrieval backend."""
import csv
from collections import deque
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
from time import perf_counter

import numpy as np
from PIL import Image, ImageDraw

SCHEMA = 1


def seconds(value):
    """Accept seconds, MM:SS or HH:MM:SS; reject negative/nonfinite times."""
    parts = str(value).split(':')
    if not 1 <= len(parts) <= 3:
        raise ValueError('Time must be seconds, MM:SS or HH:MM:SS')
    values = [float(part) for part in parts]
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('Time must be finite and nonnegative')
    if len(values) > 1 and any(v >= 60 for v in values[1:]):
        raise ValueError('Minutes/seconds after a colon must be below 60')
    return sum(value * 60 ** i for i, value in enumerate(reversed(values)))


def require_tools():
    for binary in ('ffmpeg', 'ffprobe'):
        if not shutil.which(binary):
            raise ValueError(f'{binary} is missing. macOS: brew install ffmpeg; Ubuntu: sudo apt install ffmpeg. See docs/DATA_PREPARATION.md')


def run_json(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip())
    return json.loads(result.stdout)


def probe(path):
    require_tools()
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    data = run_json(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                     '-show_streams', '-show_format', '-of', 'json', str(path)])
    if not data.get('streams'):
        raise ValueError(f'No video stream: {path}')
    stream = data['streams'][0]
    origin = float(data['format'].get('start_time', 0))
    start = float(stream.get('start_time', origin)) - origin
    duration = stream.get('duration')
    end = start + float(duration) if duration is not None else float(data['format']['duration'])
    if not math.isfinite(end) or end <= start:
        raise ValueError('Video needs a finite positive duration')
    return {'width': stream['width'], 'height': stream['height'],
            'video_start_seconds': start, 'video_end_seconds': end,
            'video_duration_seconds': end - start,
            'format_start_time': origin, 'stream_start_time': float(stream.get('start_time', origin)),
            'avg_frame_rate': stream['avg_frame_rate'], 'time_base': stream['time_base'],
            'codec': stream.get('codec_name'), 'pixel_format': stream.get('pix_fmt'),
            'duration_basis': 'video stream metadata' if duration is not None else 'container fallback',
            'ffprobe': data}


def sampled_fingerprint(path):
    """Bounded I/O identity check, explicitly NOT a full-file checksum."""
    path = Path(path)
    digest = hashlib.sha256()
    size = path.stat().st_size
    digest.update(str(size).encode())
    with path.open('rb') as stream:
        digest.update(stream.read(1024 * 1024))
        stream.seek(max(0, size - 1024 * 1024))
        digest.update(stream.read(1024 * 1024))
    return digest.hexdigest()


def full_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def init_config(source, config_path, feeds=7, hash_source=False):
    config_path, source = Path(config_path), Path(source).resolve()
    if config_path.exists():
        raise FileExistsError(config_path)
    if feeds < 1:
        raise ValueError('feeds must be positive')
    info = probe(source)
    identity = {'path': str(source), 'size_bytes': source.stat().st_size,
                'mtime_ns': source.stat().st_mtime_ns,
                'sampled_sha256': sampled_fingerprint(source), 'metadata': info}
    if hash_source:
        identity['full_sha256'] = full_hash(source)
    config = {'schema_version': SCHEMA, 'source': identity,
              'crops_verified': False,
              'coordinate_system': 'coded pixels, top-left origin; no autorotation; x,y,width,height; half-open rectangles',
              'timeline': 'seconds relative to source format.start_time, not wall-clock camera capture time',
              'encoding': {'crf': 18, 'preset': 'medium', 'threads': 4},
              'cameras': [{'id': f'camera_{i:02d}', 'description': '', 'crop': None,
                           'diagnostic_roi': None} for i in range(1, feeds + 1)]}
    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(config_path, config)
    return config


def rectangle(value, width, height):
    if not isinstance(value, list) or len(value) != 4 or any(type(v) is not int for v in value):
        raise ValueError('Crop must be [x, y, width, height] with integer coordinates')
    x, y, w, h = value
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        raise ValueError(f'Crop {value} is outside {width}x{height}')
    if any(v % 2 for v in value):
        raise ValueError('Use even x, y, width and height for reproducible yuv420p crops')
    return value


def load_config(path, verify_full_hash=False):
    config = json.loads(Path(path).read_text())
    if config['schema_version'] != SCHEMA:
        raise ValueError('Unsupported crop configuration schema')
    if type(config.get('crops_verified', False)) is not bool:
        raise ValueError('crops_verified must be a JSON boolean')
    source = Path(config['source']['path'])
    if not source.is_absolute():
        source = (Path(path).resolve().parent / source).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    expected = config['source']
    if source.stat().st_size != expected['size_bytes'] or sampled_fingerprint(source) != expected['sampled_sha256']:
        raise ValueError('Source size/sampled fingerprint changed; create a new configuration')
    if verify_full_hash:
        if 'full_sha256' not in expected:
            raise ValueError('Configuration has no full checksum; initialize with --hash-source')
        if full_hash(source) != expected['full_sha256']:
            raise ValueError('Full source SHA-256 mismatch')
    actual = probe(source)
    if any(actual[key] != expected['metadata'][key] for key in ('width', 'height', 'time_base', 'video_start_seconds', 'video_end_seconds')):
        raise ValueError('Source video metadata changed')
    ids = set()
    for camera in config['cameras']:
        name = camera['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name) or name in ids:
            raise ValueError('Camera IDs must be unique and use letters, numbers, underscore or hyphen')
        ids.add(name)
        if camera.get('crop') is not None:
            rectangle(camera['crop'], actual['width'], actual['height'])
            if camera.get('diagnostic_roi') is not None:
                rectangle(camera['diagnostic_roi'], camera['crop'][2], camera['crop'][3])
    config['source']['path'] = str(source)
    return config


def select_cameras(config, names=None):
    names = names or [c['id'] for c in config['cameras'] if c.get('crop') is not None]
    available = {c['id']: c for c in config['cameras']}
    if not names or len(set(names)) != len(names):
        raise ValueError('Define camera crops in the JSON first; select each camera at most once')
    if any(name not in available or available[name].get('crop') is None for name in names):
        raise ValueError('Unknown camera or crop not yet defined')
    return [available[name] for name in names]


def window(config, start, duration=None, end=None, profile='smoke'):
    start = seconds(start)
    if end is not None:
        finish = seconds(end)
    elif duration is not None:
        finish = start + seconds(duration)
    elif profile == 'full':
        finish = config['source']['metadata']['video_end_seconds']
    else:
        finish = start + (30 if profile == 'smoke' else 300)
    limit = config['source']['metadata']['video_end_seconds']
    if start >= limit or finish <= start or finish > limit + 1e-6:
        raise ValueError(f'Interval must be nonempty and within [0, {limit:.6f}] seconds; no silent truncation')
    if finish - start > 600 and not config.get('crops_verified', False):
        raise ValueError('Exports longer than 10 minutes are blocked until crops_verified is true after reviewing short samples')
    return start, finish


def input_command(config, start):
    return ['ffmpeg', '-hide_banner', '-nostdin', '-nostats', '-n', '-copyts', '-start_at_zero',
            '-ss', f'{start:.9f}', '-noautorotate', '-i', config['source']['path'],
            '-map', '0:v:0', '-an', '-sn', '-dn']


def crop_filter(crop):
    x, y, w, h = crop
    return f'crop={w}:{h}:{x}:{y}:exact=1'


def export_command(config, camera, start, end, output):
    settings = config['encoding']
    if type(settings['crf']) is not int or not 0 <= settings['crf'] <= 51:
        raise ValueError('crf must be an integer from 0 to 51')
    if settings['preset'] not in ('ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'):
        raise ValueError('Unsupported x264 preset')
    if type(settings['threads']) is not int or settings['threads'] <= 0:
        raise ValueError('threads must be a positive integer')
    filters = f'trim=start={start:.9f}:end={end:.9f},{crop_filter(camera["crop"])},showinfo,setpts=PTS-STARTPTS'
    return input_command(config, start) + [
        '-t', f'{end-start:.9f}', '-vf', filters, '-c:v', 'libx264',
        '-crf', str(settings['crf']), '-preset', settings['preset'],
        '-threads', str(settings['threads']), '-bf', '0', '-enc_time_base:v', 'filter',
        '-fps_mode', 'passthrough', '-pix_fmt', 'yuv420p',
        '-video_track_timescale', '1000000', '-movflags', '+faststart', str(output)]


class ShowInfo:
    """Parse integer PTS plus rational time base, avoiding rounded pts_time logs."""
    def __init__(self):
        self.time_base = None

    def parse(self, line):
        if 'showinfo' not in line:
            return None
        match = re.search(r'config in time_base:\s*(\d+/\d+)', line)
        if match:
            self.time_base = Fraction(match[1])
        match = re.search(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s', line)
        if match:
            if self.time_base is None:
                raise ValueError('FFmpeg did not report filter time base')
            return int(match[1]), Fraction(int(match[2])) * self.time_base
        return None


def validate_timeline(video, timeline):
    """Stream encoded packet timestamps and compare to every source/output row."""
    command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_packets',
               '-show_entries', 'packet=pts_time', '-of', 'csv=p=0', str(video)]
    count, max_error = 0, 0.
    # Errors are normally tiny; stderr goes to a file rather than an undrained pipe.
    import tempfile
    with tempfile.TemporaryFile() as errors, Path(timeline).open(newline='') as stream:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True)
        try:
            rows = iter(csv.DictReader(stream))
            for line in process.stdout:
                if not line.strip():
                    continue
                row = next(rows, None)
                if row is None:
                    raise ValueError('Output has more frames than the source timestamp mapping')
                error = abs(float(line.strip().split(',')[0]) - float(row['cropped_seconds']))
                if error > 0.000002:
                    raise ValueError(f'Encoded timestamp mismatch at frame {count}: {error} s')
                max_error = max(max_error, error)
                count += 1
            if process.wait() != 0:
                errors.seek(0)
                raise ValueError(errors.read().decode(errors='replace'))
            if next(rows, None) is not None or count == 0:
                raise ValueError('Frame count differs from source timestamp mapping, or output is empty')
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait()
            process.stdout.close()
    return {'frames': count, 'maximum_timestamp_error_seconds': max_error}


def export_cameras(config, cameras, start, end, output, dry_run=False):
    if end - start > 600 and not config.get('crops_verified', False):
        raise ValueError('Long exports are blocked until crops_verified is true after short-sample review')
    output = Path(output)
    if output.exists():
        raise FileExistsError(f'Use a new output directory: {output}')
    plans = [(camera, export_command(config, camera, start, end, output / f'{camera["id"]}.mp4')) for camera in cameras]
    if dry_run:
        return {'commands': [cmd for _, cmd in plans]}
    output.mkdir(parents=True)
    write_json(output / 'crop_config.json', config)
    manifest = {'status': 'running', 'source': config['source'], 'requested_start_seconds': start,
                'requested_end_seconds_exclusive': end, 'cameras': [],
                'ffmpeg_version': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
                'timeline_rule': 'source_seconds = first_retained_source_seconds + cropped_seconds; see per-frame CSV (<=2 us output quantization)',
                'boundary_policy': 'Keep decoded PTS in [start,end); rebase first retained frame to zero. No boundary padding or FPS conversion. Sparse VFR means playable length may be shorter than requested interval.',
                'audio': 'excluded; video-only camera exports', 'rotation': 'no autorotation'}
    write_json(output / 'manifest.json', manifest)
    try:
        for camera, command in plans:
            print(f'Exporting {camera["id"]}: {start:.3f}–{end:.3f} s', flush=True)
            began = perf_counter()
            parser, tail = ShowInfo(), deque(maxlen=40)
            timeline = output / f'{camera["id"]}.timeline.csv'
            first, last, count = None, None, 0
            with timeline.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['frame', 'source_seconds', 'cropped_seconds'])
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                try:
                    for line in process.stderr:
                        tail.append(line)
                        entry = parser.parse(line)
                        if entry is not None:
                            number, timestamp = entry
                            if number != count or (last is not None and timestamp <= last):
                                raise ValueError('Unexpected frame order or non-increasing source timestamps')
                            if not start - 1e-8 <= float(timestamp) < end + 1e-8:
                                raise ValueError('Exported frame lies outside requested source interval')
                            if first is None:
                                first = timestamp
                            writer.writerow([number, f'{float(timestamp):.12f}', f'{float(timestamp-first):.12f}'])
                            last, count = timestamp, count + 1
                    if process.wait() != 0:
                        raise ValueError('FFmpeg export failed:\n' + ''.join(tail))
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait()
                    process.stderr.close()
            path = output / f'{camera["id"]}.mp4'
            verified = validate_timeline(path, timeline)
            info = probe(path)
            if (info['width'], info['height']) != tuple(camera['crop'][2:]):
                raise ValueError('Export dimensions do not match crop')
            manifest['cameras'].append({
                'id': camera['id'], 'crop': camera['crop'], 'video': path.name,
                'timeline_csv': timeline.name, 'first_retained_source_seconds': float(first),
                'last_retained_source_seconds': float(last), 'verified_timeline': verified,
                'video_metadata': info, 'elapsed_seconds': perf_counter()-began,
                'bytes': path.stat().st_size, 'sha256': full_hash(path), 'command': command})
            write_json(output / 'manifest.json', manifest)
        manifest['status'] = 'complete'
    except BaseException as error:
        manifest['status'] = 'failed'
        manifest['error'] = str(error)
        raise
    finally:
        write_json(output / 'manifest.json', manifest)
    return manifest


def preview(config, at, output):
    at = seconds(at)
    if at >= config['source']['metadata']['video_end_seconds']:
        raise ValueError('Preview time lies outside the video')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    command = ['ffmpeg', '-v', 'error', '-nostdin', '-ss', str(at), '-noautorotate',
               '-i', config['source']['path'], '-map', '0:v:0', '-frames:v', '1',
               '-f', 'image2pipe', '-c:v', 'png', '-']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode or not result.stdout:
        raise ValueError(result.stderr.decode(errors='replace'))
    image = Image.open(io.BytesIO(result.stdout)).convert('RGB')
    image.save(output / 'source.png')
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    for x in range(0, image.width, 100):
        draw.line((x, 0, x, image.height), fill='yellow', width=1)
        draw.text((x+2, 2), str(x), fill='black', stroke_width=1, stroke_fill='yellow')
    for y in range(0, image.height, 100):
        draw.line((0, y, image.width, y), fill='yellow', width=1)
        draw.text((2, y+2), str(y), fill='black', stroke_width=1, stroke_fill='yellow')
    for camera in config['cameras']:
        if camera.get('crop') is None:
            continue
        x, y, w, h = camera['crop']
        draw.rectangle((x, y, x+w-1, y+h-1), outline='red', width=3)
        draw.text((x+4, y+16), camera['id'], fill='white', stroke_width=2, stroke_fill='black')
        image.crop((x, y, x+w, y+h)).save(output / f'{camera["id"]}.png')
    overlay.save(output / 'coordinates.png')
    write_json(output / 'preview.json', {'requested_source_seconds': at, 'note': 'First decoded frame at/after request, not an exact frame timestamp measurement', 'command': command, 'configuration': config})


def gray_frames(config, camera, start, end):
    """Stream bounded grayscale frames and exact source PTS; drain stderr concurrently."""
    x, y, w, h = camera['crop']
    if camera.get('diagnostic_roi') is not None:
        rx, ry, w, h = camera['diagnostic_roi']
        x, y = x + rx, y + ry
    width, height = 160, 90
    filters = (f'trim=start={start:.9f}:end={end:.9f},{crop_filter([x,y,w,h])},'
               f'scale={width}:{height}:flags=area,format=gray,showinfo,setpts=PTS-STARTPTS')
    command = input_command(config, start) + ['-t', str(end-start), '-vf', filters,
        '-c:v', 'rawvideo', '-threads', '1', '-enc_time_base:v', 'filter',
        '-fps_mode', 'passthrough', '-f', 'rawvideo', 'pipe:1']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    messages, stop = queue.Queue(maxsize=128), threading.Event()
    errors = deque(maxlen=30)

    def send(value):
        while not stop.is_set():
            try:
                messages.put(value, timeout=.1)
                return
            except queue.Full:
                pass

    def read_timestamps():
        parser = ShowInfo()
        try:
            for raw in process.stderr:
                line = raw.decode(errors='replace')
                errors.append(line)
                entry = parser.parse(line)
                if entry is not None:
                    send(entry)
        except Exception as error:
            send(error)
        finally:
            send(None)

    reader = threading.Thread(target=read_timestamps, daemon=True)
    reader.start()
    try:
        number = 0
        while True:
            raw = process.stdout.read(width * height)
            if not raw:
                break
            if len(raw) != width * height:
                raise ValueError('Truncated raw diagnostic frame')
            try:
                entry = messages.get(timeout=60)
            except queue.Empty:
                raise ValueError('No diagnostic frame timestamp received') from None
            if entry is None or isinstance(entry, Exception) or entry[0] != number:
                raise ValueError(f'Diagnostic frame/timestamp mismatch: {entry}')
            yield float(entry[1]), np.frombuffer(raw, dtype=np.uint8).reshape(height, width), command
            number += 1
        if process.wait() != 0:
            raise ValueError('FFmpeg diagnostic failed:\n' + ''.join(errors))
        if number == 0:
            raise ValueError('No frames in diagnostic window')
    finally:
        stop.set()
        if process.poll() is None:
            process.terminate()
            process.wait()
        reader.join(timeout=5)
        process.stdout.close()
        process.stderr.close()


def diagnose(config, camera, start, end, output, mad_threshold=2., pixel_delta=8., min_fraction=.01):
    if not all(math.isfinite(v) for v in (mad_threshold, pixel_delta, min_fraction)):
        raise ValueError('Diagnostic thresholds must be finite')
    if mad_threshold <= 0 or not 0 < pixel_delta <= 255 or not 0 < min_fraction <= 1:
        raise ValueError('Thresholds: MAD > 0, 0 < pixel-delta <= 255, 0 < min-fraction <= 1')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    previous, first, last = None, None, None
    count, changes, exact_repeats, near_black_frames = 0, 0, 0, 0
    first_change, last_change = None, None
    with (output / 'differences.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['frame', 'source_seconds', 'mean_absolute_difference', 'changed_pixel_fraction', 'observable_update', 'mean_luma', 'dark_pixel_fraction', 'near_black'])
        for timestamp, gray, command in gray_frames(config, camera, start, end):
            if last is not None and timestamp <= last:
                raise ValueError('Non-increasing timestamps in diagnostic')
            if first is None:
                first = timestamp
            mad, fraction, changed = 0., 0., False
            if previous is not None:
                delta = np.abs(gray.astype(np.int16) - previous.astype(np.int16))
                mad = float(delta.mean())
                fraction = float(np.mean(delta >= pixel_delta))
                changed = mad >= mad_threshold and fraction >= min_fraction
                exact_repeats += int(not delta.any())
                if changed:
                    changes += 1
                    if first_change is None:
                        first_change = timestamp
                    last_change = timestamp
            dark_fraction = float(np.mean(gray <= 16))
            near_black = dark_fraction >= .99
            near_black_frames += int(near_black)
            writer.writerow([count, f'{timestamp:.12f}', mad, fraction, int(changed), float(gray.mean()), dark_fraction, int(near_black)])
            previous, last = gray, timestamp
            count += 1
    span = last - first
    if span <= 0:
        raise ValueError('Diagnostic needs at least two frames')
    report = {
        'camera': camera, 'requested_start_seconds': start, 'requested_end_seconds_exclusive': end,
        'first_source_seconds': first, 'last_source_seconds': last, 'observed_span_seconds': span,
        'decoded_frames': count, 'observed_recording_fps': (count-1)/span,
        'observable_updates': changes, 'observable_update_hz': changes/span,
        'inter_update_hz': (changes-1)/(last_change-first_change) if changes > 1 and last_change > first_change else None,
        'exact_repeated_pair_fraction': exact_repeats/(count-1),
        'near_black_frame_fraction': near_black_frames/count,
        'near_black_definition': 'at least 99% of analyzed grayscale pixels <= 16; per-frame timestamps in differences.csv; not proof of camera failure',
        'thresholds': {'mad_threshold_0_255': mad_threshold, 'pixel_delta_0_255': pixel_delta,
                       'min_changed_fraction': min_fraction},
        'analysis_image': '160x90 grayscale, area downsampling; every decoded frame; no temporal subsampling',
        'limitations': 'Observable image-change rate, not true network refresh or sensor FPS. Static scenes can refresh invisibly; compression noise, clocks, overlays, reconnects and occlusion can mimic updates. Inspect ROI and sensitivity across thresholds/windows.',
        'source': config['source'], 'command': command,
    }
    write_json(output / 'diagnostic.json', report)
    return report
