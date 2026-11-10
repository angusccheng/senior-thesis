"""FFmpeg integration tests with a tiny known grid; no real footage required."""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import cv2
import numpy as np

from video_search.preprocessing import (ShowInfo, diagnose, export_cameras, init_config,
                           load_config, rectangle, select_cameras, seconds, window)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/ffprobe not installed')
class PreprocessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'known_grid.mp4'
        cls.crop_a, cls.crop_b = [4, 4, 92, 92], [104, 4, 92, 92]
        command = ['ffmpeg', '-v', 'error', '-nostdin', '-f', 'rawvideo', '-pixel_format',
                   'rgb24', '-video_size', '200x100', '-framerate', '10', '-i', 'pipe:0',
                   '-c:v', 'libx264', '-crf', '0', '-bf', '0', '-pix_fmt', 'yuv420p', str(cls.source)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        for i in range(40):
            image = np.zeros((100, 200, 3), dtype=np.uint8)
            image[:, :100] = [80 + 80 * ((i // 10) % 2), 20, 20]  # 1 Hz changes
            image[:, 100:] = [0, 0, 0]  # black/static feed
            process.stdin.write(image.tobytes())
        process.stdin.close()
        stderr = process.stderr.read()
        process.stderr.close()
        if process.wait() != 0:
            raise RuntimeError(stderr.decode())
        cls.config_path = cls.root / 'crops.json'
        cls.config = init_config(cls.source, cls.config_path, feeds=2, hash_source=True)
        cls.config['cameras'][0]['crop'] = cls.crop_a
        cls.config['cameras'][1]['crop'] = cls.crop_b
        cls.config['encoding']['preset'] = 'ultrafast'
        cls.config_path.write_text(json.dumps(cls.config))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_config_and_input_validation(self):
        self.assertEqual(len(load_config(self.config_path, verify_full_hash=True)['cameras']), 2)
        with self.assertRaises(FileExistsError):
            init_config(self.source, self.config_path)
        with self.assertRaises(FileNotFoundError):
            init_config(self.root / 'missing.mov', self.root / 'no.json')
        for bad in ([0, 0, 201, 100], [1, 0, 92, 92], [-2, 0, 92, 92], [0, 0, 0, 92]):
            with self.subTest(crop=bad), self.assertRaises(ValueError):
                rectangle(bad, 200, 100)
        with self.assertRaises(ValueError):
            select_cameras(self.config, ['unknown'])

    def test_window_and_full_export_gate(self):
        self.assertEqual(seconds('01:02:03.5'), 3723.5)
        self.assertEqual(window(self.config, '1.05', duration='1'), (1.05, 2.05))
        self.assertEqual(window(self.config, 0, profile='full'), (0, 4))
        for value in ('nan', 'inf', '-1', '00:99'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                seconds(value)
        with self.assertRaises(ValueError):
            window(self.config, 0, duration=30)  # no silently shortened smoke test
        long = json.loads(json.dumps(self.config))
        long['source']['metadata']['video_end_seconds'] = 18000
        with self.assertRaisesRegex(ValueError, 'crops_verified'):
            window(long, 0, profile='full')
        self.assertEqual(window(long, 0, profile='dev'), (0, 300))
        self.assertEqual(window(long, 0, duration=600), (0, 600))

    def test_fractional_clip_crop_and_timestamps(self):
        output = self.root / 'fractional'
        result = export_cameras(self.config, self.config['cameras'], 1.05, 2.05, output)
        self.assertEqual(result['status'], 'complete')
        for camera in result['cameras']:
            self.assertEqual(camera['verified_timeline']['frames'], 10)
            self.assertAlmostEqual(camera['first_retained_source_seconds'], 1.1)
            with (output / camera['timeline_csv']).open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            np.testing.assert_allclose([float(r['source_seconds']) for r in rows], np.arange(11, 21) / 10)
            np.testing.assert_allclose([float(r['cropped_seconds']) for r in rows], np.arange(10) / 10)
            cap = cv2.VideoCapture(str(output / camera['video']))
            ok, bgr = cap.read()
            cap.release()
            self.assertTrue(ok)
            self.assertEqual(bgr.shape[:2], (92, 92))
            if camera['id'] == 'camera_01':
                self.assertGreater(bgr[:, :, 2].mean(), 145)  # red view only
                self.assertLess(bgr[:, :, 0].mean(), 30)
            else:
                self.assertLess(bgr.mean(), 2)  # black view only
        with self.assertRaises(FileExistsError):
            export_cameras(self.config, self.config['cameras'], 1.05, 2.05, output)

    def test_full_mode_on_tiny_source_and_dry_run(self):
        start, end = window(self.config, 0, profile='full')
        dry_output = self.root / 'dry_run'
        plans = export_cameras(self.config, self.config['cameras'], start, end, dry_output, dry_run=True)
        self.assertEqual(len(plans['commands']), 2)
        self.assertFalse(dry_output.exists())
        result = export_cameras(self.config, self.config['cameras'][:1], start, end, self.root / 'full_tiny')
        self.assertEqual(result['cameras'][0]['verified_timeline']['frames'], 40)

    def test_effective_update_frequency_and_blackout(self):
        moving = diagnose(self.config, self.config['cameras'][0], 0, 4, self.root / 'moving')
        self.assertEqual(moving['decoded_frames'], 40)
        self.assertEqual(moving['observable_updates'], 3)
        self.assertAlmostEqual(moving['observed_recording_fps'], 10)
        self.assertAlmostEqual(moving['inter_update_hz'], 1)
        black = diagnose(self.config, self.config['cameras'][1], 0, 4, self.root / 'black')
        self.assertEqual(black['observable_updates'], 0)
        self.assertEqual(black['near_black_frame_fraction'], 1)
        self.assertEqual(black['exact_repeated_pair_fraction'], 1)

    def test_showinfo_uses_integer_pts_not_rounded_time(self):
        parser = ShowInfo()
        parser.parse('[Parsed_showinfo_2] config in time_base: 1/600, frame_rate: 60/1')
        number, timestamp = parser.parse('[Parsed_showinfo_2] n: 0 pts: 18470 pts_time:30.7833 duration: 430')
        self.assertEqual(number, 0)
        self.assertAlmostEqual(float(timestamp), 18470/600, places=12)


if __name__ == '__main__':
    unittest.main()
