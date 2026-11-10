"""Diversity coverage, deterministic budgets and shared index/retrieval behavior."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from video_search.samplers import DiversitySampler
from video_search.pipeline import build_index, load_index, search_index, sha256_file
from video_search.video import FrameInfo
from test_baseline import ColorEncoder
from video_search.experiments import load_catalog, command


class DiversityTests(unittest.TestCase):
    def test_known_vectors_choose_coverage_and_return_chronological_positions(self):
        v=np.array([[1,0],[1,0],[0,1],[-1,0],[0,-1]],dtype=np.float32)
        # Start 0, then opposite 3, then tied orthogonal 2 before 4.
        np.testing.assert_array_equal(DiversitySampler(3).select_embeddings(v),[0,2,3])
        np.testing.assert_array_equal(DiversitySampler(1).select_embeddings(v),[0])
        np.testing.assert_array_equal(DiversitySampler(99).select_embeddings(v),range(5))
        self.assertEqual(DiversitySampler(3).select([FrameInfo(0,0)]),[FrameInfo(0,0)])

    def test_identical_vectors_have_unique_stable_choices(self):
        v=np.tile(np.array([[1,0]],dtype=np.float32),(10,1))
        for _ in range(3):
            np.testing.assert_array_equal(DiversitySampler(4).select_embeddings(v),range(4))

    def test_invalid_budgets_and_features(self):
        for budget in (0,-1,1.5,True):
            with self.assertRaises(ValueError):DiversitySampler(budget)
        for v in (np.empty((0,2)),np.array([[0,0]]),np.array([[float('nan'),0]]),np.array([[2,0]])):
            with self.assertRaises(ValueError):DiversitySampler(2).select_embeddings(v)

    def test_catalog_and_command_carry_diversity_budget(self):
        root=Path(__file__).resolve().parents[1]
        spec=next(s for s in load_catalog(root)['experiments'] if s['method']=='diversity')
        args=command(spec)
        self.assertEqual(args[args.index('--method')+1],'diversity')
        self.assertEqual(args[args.index('--max-frames')+1],'120')
        self.assertNotIn('--interval',args)

    def test_catalog_rejects_settings_that_would_be_ignored(self):
        root=Path(__file__).resolve().parents[1]
        catalog=load_catalog(root)
        for method in ('uniform','diversity'):
            spec=dict(next(s for s in catalog['experiments'] if s['method']==method))
            spec.update(max_frames=120,interval_seconds=5)
            with tempfile.TemporaryDirectory() as temp:
                Path(temp,'catalog.json').write_text(json.dumps({'schema_version':1,'experiments':[spec]}))
                with self.assertRaises(ValueError):load_catalog(temp,'catalog.json')

    def test_saved_subset_source_times_eligibility_and_no_reencoding_on_search(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);video=root/'colors.mp4'
            writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(64,48))
            self.assertTrue(writer.isOpened())
            for color in [(0,0,255)]*10+[(0,255,0)]*10+[(255,0,0)]*10:
                writer.write(np.full((48,64,3),color,dtype=np.uint8))
            writer.release()
            mapping=root/'timeline.csv'
            with mapping.open('w',newline='') as stream:
                w=csv.writer(stream);w.writerow(['frame','source_seconds','cropped_seconds'])
                for i in range(30):w.writerow([i,100+i/10,i/10])
            manifest=root/'dataset.json'
            manifest.write_text(json.dumps({'schema_version':1,'camera_id':'colors',
                'video':{'sha256':sha256_file(video)},
                'timestamp_mapping':{'path':str(mapping),'sha256':sha256_file(mapping)},
                'valid_source_intervals':[[100,101],[102,103]],
                'availability_policy':'exclude_confirmed_unavailable_only'}))
            encoder=ColorEncoder();index=root/'index.npz'
            report=build_index(video,DiversitySampler(2),encoder,index,batch_size=7,dataset_manifest=manifest)
            e,t,n,meta=load_index(index)
            self.assertEqual(e.shape,(2,3))
            self.assertEqual(report['candidate_frames_encoded'],20)
            self.assertEqual(meta['eligibility']['excluded_candidates'],10)
            self.assertTrue(all(x<10 or x>=20 for x in n))
            self.assertTrue(any(x<10 for x in n) and any(x>=20 for x in n))
            self.assertIn('diversity_selection',report['indexing_stage_timings'])
            with np.load(index,allow_pickle=False) as data:
                np.testing.assert_allclose(data['source_timestamps'],t+100)
            with patch.object(encoder,'encode_images',side_effect=AssertionError('re-encoded')):
                rows,_=search_index(index,'red',encoder)
            self.assertEqual(len(rows),2)
            self.assertLess(rows[0]['seconds'],1)
            self.assertGreater(rows[0]['cosine_similarity'],.99)
            second=root/'second.npz'
            build_index(video,DiversitySampler(2),encoder,second,batch_size=7,dataset_manifest=manifest)
            for actual,expected in zip(load_index(second)[:3],(e,t,n)):
                np.testing.assert_array_equal(actual,expected)


if __name__=='__main__':unittest.main()
