"""Offline regression tests; the real OpenCLIP smoke test is documented separately."""
import json
import csv
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from video_search.pipeline import build_index, export_previews, load_index, rank_frames, search_index
from video_search.samplers import UniformSampler
from video_search.video import FrameInfo, scan_video, selected_frames, video_properties


class ColorEncoder:
    """Deterministic test double: exercises storage/ranking without downloads."""
    preprocess = 'RGB test transform'

    def metadata(self):
        return dict(model='test', pretrained='test', weights_sha256='test', precision='fp32')

    def encode_images(self, images):
        features = np.stack([np.asarray(im).mean(axis=(0, 1)) for im in images]).astype(np.float32)
        return features / np.linalg.norm(features, axis=1, keepdims=True)

    def encode_text(self, text):
        return np.array([1, 0, 0], dtype=np.float32)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.video = self.root / 'colors.mp4'
        writer = cv2.VideoWriter(str(self.video), cv2.VideoWriter_fourcc(*'mp4v'), 10, (64, 48))
        self.assertTrue(writer.isOpened())
        for i in range(40):
            bgr = (0, 0, 255) if i < 20 else (255, 0, 0)
            writer.write(np.full((48, 64, 3), bgr, dtype=np.uint8))
        writer.release()

    def tearDown(self):
        self.temp.cleanup()

    def test_decoded_timestamps_and_exact_selection(self):
        properties = video_properties(self.video)
        self.assertEqual(properties['fps'], 10)
        self.assertEqual(properties['duration_seconds'], 4)
        self.assertEqual(properties['reported_frame_count'], 40)
        timeline = scan_video(self.video)
        self.assertEqual(len(timeline), 40)
        np.testing.assert_allclose([f.seconds for f in timeline], np.arange(40) / 10, atol=1e-6)
        chosen = UniformSampler(0.25).select(timeline)
        self.assertEqual([f.number for f in chosen[:4]], [0, 3, 5, 8])
        decoded = list(selected_frames(self.video, chosen))
        self.assertEqual([info for info, _ in decoded], chosen)
        self.assertGreater(decoded[0][1][:, :, 0].mean(), 250)  # RGB, not BGR

    def test_budget_covers_full_timeline(self):
        frames = scan_video(self.video)
        selected = UniformSampler(0.5, max_frames=3).select(frames)
        self.assertEqual([f.number for f in selected], [0, 15, 35])
        self.assertEqual(len(UniformSampler(0.001).select(frames)), 40)

    def test_variable_timestamp_grid(self):
        frames = [FrameInfo(i, t) for i, t in enumerate([0, .04, .2, .21, .7, 1.05])]
        self.assertEqual([f.number for f in UniformSampler(.1).select(frames)], [0, 2, 4, 5])

    def test_invalid_sampler_settings(self):
        for value in (0, -1, float('nan'), float('inf')):
            with self.subTest(interval=value), self.assertRaises(ValueError):
                UniformSampler(value)
        with self.assertRaises(ValueError):
            UniformSampler(max_frames=0)

    def test_cosine_ranking_and_stable_ties(self):
        embeddings = np.array([[0, 1], [1, 0], [1, 0], [-1, 0]], dtype=np.float32)
        winners, scores = rank_frames(embeddings, np.array([1, 0]), 5)
        self.assertEqual(winners.tolist(), [1, 2, 0, 3])
        np.testing.assert_array_equal(scores, [0, 1, 1, -1])
        with self.assertRaises(ValueError):
            rank_frames(embeddings, np.array([1, 0]), 0)
        with self.assertRaises(ValueError):
            rank_frames(embeddings, np.array([2, 0]), 5)

    def test_index_search_and_previews(self):
        encoder = ColorEncoder()
        index = self.root / 'index.npz'
        report = build_index(self.video, UniformSampler(.5), encoder, index, batch_size=3)
        embeddings, timestamps, numbers, meta = load_index(index)
        self.assertEqual(embeddings.shape, (8, 3))
        self.assertEqual(report['storage']['payload_bytes'], 8 * (3 * 4 + 8 + 8))
        self.assertEqual(report['index_file_bytes'], index.stat().st_size)
        stages = report['indexing_stage_timings']
        self.assertEqual(stages['image_encoding_including_preprocess']['calls'], 3)
        self.assertIn('timeline_decoding', stages)
        self.assertIn('selected_frame_decoding', stages)
        self.assertIn('index_persistence', stages)
        self.assertTrue(all(value['seconds'] >= 0 for value in stages.values()))
        self.assertLessEqual(sum(value['seconds'] for value in stages.values()), report['indexing_seconds'])
        self.assertEqual(meta['source']['decoded_frames'], 40)
        self.assertEqual(meta['source']['duration_seconds'], 4)
        self.assertEqual(meta['source']['fps'], 10)
        rows, meta = search_index(index, 'red', encoder)
        self.assertEqual(len(rows), 5)
        self.assertLess(rows[0]['seconds'], 2)
        self.assertGreater(rows[0]['cosine_similarity'], .99)
        relocated = self.video.with_name('relocated.mp4')
        self.video.rename(relocated)
        without_source, _ = search_index(index, 'red', encoder)
        self.assertEqual(without_source, rows)
        relocated.rename(self.video)
        output = self.root / 'matches'
        output.mkdir()
        export_previews(rows, meta, output)
        self.assertEqual(len(list(output.glob('*.jpg'))), 5)
        self.assertEqual(json.loads(index.with_suffix('.metadata.json').read_text())['index_sha256'], report['index_sha256'])
        with self.assertRaises(FileExistsError):
            build_index(self.video, UniformSampler(), encoder, index)
        with self.assertRaises(ValueError):
            search_index(index, '  ', encoder)
        encoder.metadata = lambda: dict(model='wrong')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            search_index(index, 'red', encoder)
        with self.video.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            export_previews(rows, meta, output)

    def test_invalid_video_and_index(self):
        bad = self.root / 'empty.mp4'
        bad.write_bytes(b'')
        with self.assertRaises(ValueError):
            scan_video(bad)
        with self.assertRaises(FileNotFoundError):
            scan_video(self.root / 'missing.mp4')
        index = self.root / 'broken.npz'
        np.savez(index, embeddings=np.array([[3, 4]], dtype=np.float32),
                 timestamps=np.array([0.]), frame_numbers=np.array([0], dtype=np.int64),
                 metadata=np.array(json.dumps({'schema_version': 1})))
        with self.assertRaisesRegex(ValueError, 'unit vectors'):
            load_index(index)

    def test_dataset_eligibility_and_original_timestamps(self):
        from video_search.pipeline import sha256_file
        mapping = self.root / 'timeline.csv'
        with mapping.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['frame', 'source_seconds', 'cropped_seconds'])
            for i in range(40):
                writer.writerow([i, 100+i/10, i/10])
        manifest = self.root / 'dataset.json'
        data = {'schema_version': 1, 'camera_id': 'red_camera',
                'video': {'sha256': sha256_file(self.video)},
                'timestamp_mapping': {'path': str(mapping), 'sha256': sha256_file(mapping)},
                'valid_source_intervals': [[100, 101], [102, 104]],
                'availability_policy': 'exclude_confirmed_unavailable_only'}
        manifest.write_text(json.dumps(data))
        index = self.root / 'dataset_index.npz'
        report = build_index(self.video, UniformSampler(.5), ColorEncoder(), index,
                             batch_size=3, dataset_manifest=manifest)
        e,t,n,m = load_index(index)
        np.testing.assert_allclose(t, [0, .5, 2, 2.5, 3, 3.5])
        self.assertEqual(m['eligibility']['excluded_candidates'], 2)
        with np.load(index, allow_pickle=False) as archive:
            np.testing.assert_allclose(archive['source_timestamps'], t+100)
        rows, _ = search_index(index, 'red', ColorEncoder())
        self.assertTrue(all(row['camera_id']=='red_camera' for row in rows))
        self.assertTrue(all(abs(row['source_seconds']-row['seconds']-100)<1e-9 for row in rows))
        self.assertIn('indexing_seconds', report)
        mapping.write_text(mapping.read_text()+'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            build_index(self.video, UniformSampler(.5), ColorEncoder(), self.root/'bad.npz', dataset_manifest=manifest)


if __name__ == '__main__':
    unittest.main()
