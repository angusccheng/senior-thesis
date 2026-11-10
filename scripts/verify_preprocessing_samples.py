"""Verify selected decoded camera frames against source crops and make a review sheet."""
import argparse
import csv
import io
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from video_search.preprocessing import crop_filter, input_command, load_config, sampled_fingerprint, write_json


def verify(config_path, sample_dir, review_dir='review'):
    config = load_config(config_path)
    sample_dir = Path(sample_dir)
    manifest = json.loads((sample_dir / 'manifest.json').read_text())
    if manifest['status'] != 'complete':
        raise ValueError('Export manifest is incomplete')
    review = sample_dir / review_dir
    review.mkdir(exist_ok=False)
    evidence = {'source_unchanged': False, 'cameras': [], 'crops_approved': config.get('crops_verified', False), 'note': 'Source/cropped frame MAE uses lossy H.264 tolerance <=6 gray levels; first/middle/last frames checked.'}
    sheet = Image.new('RGB', (1120, 870), 'white')
    draw = ImageDraw.Draw(sheet)
    for position, item in enumerate(manifest['cameras']):
        with (sample_dir / item['timeline_csv']).open(newline='') as stream:
            rows = list(csv.DictReader(stream))  # Only the short smoke-test mapping.
        total = len(rows)
        indices = {0, total//2, total-1}
        cap = cv2.VideoCapture(str(sample_dir / item['video']))
        checks = []
        decoded = 0
        try:
            while True:
                ok, bgr = cap.read()
                if not ok:
                    break
                row = rows[decoded]
                pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                if abs(pts-float(row['cropped_seconds'])) > 2e-6:
                    raise ValueError('OpenCV timestamp does not match crop/source mapping')
                if decoded in indices:
                    source_time = float(row['source_seconds'])
                    filters = f'trim=start={source_time-1e-9:.12f},{crop_filter(item["crop"])}'
                    command = input_command(config, max(0, source_time-1)) + ['-loglevel', 'error',
                        '-vf', filters, '-frames:v', '1', '-f', 'image2pipe', '-c:v', 'png', 'pipe:1']
                    result = subprocess.run(command, capture_output=True)
                    if result.returncode:
                        raise ValueError(result.stderr.decode(errors='replace'))
                    expected = np.asarray(Image.open(io.BytesIO(result.stdout)).convert('RGB'))
                    actual = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    if expected.shape != actual.shape:
                        raise ValueError('Crop dimensions differ from expected source region')
                    mae = float(np.abs(expected.astype(np.float32)-actual.astype(np.float32)).mean())
                    if mae > 6:
                        raise ValueError(f'{item["id"]} frame {decoded}: source/crop MAE {mae} exceeds tolerance')
                    checks.append({'frame': decoded, 'source_seconds': source_time, 'cropped_seconds': pts,
                                   'mean_absolute_pixel_error': mae})
                    if decoded == 0:
                        image = Image.fromarray(actual)
                        image.save(review / f'{item["id"]}.png')
                        thumb = ImageOps.contain(image, (352, 242))
                        x, y = (position % 3)*372, (position // 3)*290
                        draw.text((x+8, y+4), item['id'], fill='black')
                        draw.text((x+8, y+20), f'source {source_time:.6f}s', fill='black')
                        sheet.paste(thumb, (x+8, y+40))
                decoded += 1
        finally:
            cap.release()
        if decoded != total:
            raise ValueError('Decoded cropped-frame count differs from timestamp mapping')
        evidence['cameras'].append({'id': item['id'], 'decoded_frames': decoded,
                                    'dimensions': item['crop'][2:], 'checks': checks})
    source = Path(config['source']['path'])
    evidence['source_unchanged'] = (source.stat().st_size == config['source']['size_bytes']
        and source.stat().st_mtime_ns == config['source']['mtime_ns']
        and sampled_fingerprint(source) == config['source']['sampled_sha256'])
    if not evidence['source_unchanged']:
        raise ValueError('Source metadata/fingerprint changed')
    sheet.save(review / 'contact_sheet.jpg', quality=95)
    evidence['passed'] = True
    write_json(review / 'verification.json', evidence)
    print(f'PASS: {len(evidence["cameras"])} crops, first/middle/last pixel checks, all decoded timestamps, source unchanged.')
    print(f'Review sheet: {review / "contact_sheet.jpg"}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--samples', required=True)
    parser.add_argument('--review-dir', default='review', help='New review subdirectory; existing evidence is preserved')
    args = parser.parse_args()
    verify(args.config, args.samples, args.review_dir)
