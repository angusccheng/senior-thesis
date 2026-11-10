"""Reporting must preserve provenance, missing measurements and run identity."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from video_search.reporting import collect, experiment_row, generate, read_json, summary_stats, terminal_table, terminal_results

ROOT = Path(__file__).resolve().parents[1]


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.registry = read_json(ROOT, 'experiments/registry.json')
        self.spec = self.registry['experiments'][0]
        self.record = read_json(ROOT, self.spec['benchmark_record'])
        self.evidence = read_json(ROOT, self.spec['evidence'])

    def row(self):
        return experiment_row(self.spec, self.record, self.evidence)

    def test_current_run_and_measurement_scopes(self):
        rows = collect(ROOT, self.registry)
        self.assertEqual([r['experiment_id'] for r in rows],
                         [s['experiment_id'] for s in self.registry['experiments']
                          if s['status'] in ('current','completed')])
        row = rows[0]
        self.assertEqual(row['index_bytes'], 285146)
        self.assertEqual(row['indexed_item_count'], 120)
        self.assertEqual(row['embedding_dimensions'], 512)
        self.assertEqual(row['indexing_n'], 1)
        self.assertEqual(row['fresh_query_with_previews_n'], 6)
        self.assertEqual(row['warm_query_without_previews_n'], 9)
        self.assertAlmostEqual(row['fresh_query_with_previews_median_s'], 7.417582416499499)
        self.assertAlmostEqual(row['warm_query_without_previews_median_s'], .03653529193252325)
        for key in ('query_hit_at_5', 'cpu_model', 'physical_ram_bytes',
                    'indexing_sample_stddev_s', 'fresh_query_with_previews_p95_s',
                    'stage_selection_s'):
            self.assertIsNone(row[key], key)
        self.assertEqual(row['stages_status'], 'unavailable')
        self.assertTrue(row['quality_reason'])
        self.assertIn('historical', row['cpu_model_reason'])

    def test_audit_cannot_become_an_extra_experiment(self):
        duplicate = copy.deepcopy(self.registry)
        duplicate['experiments'].append(copy.deepcopy(self.spec))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            collect(ROOT, duplicate)
        self.spec['experiment_id'] = 'fake_audit_run'
        with self.assertRaisesRegex(ValueError, 'audit'):
            self.row()

    def test_failed_or_misattributed_evidence_is_rejected(self):
        self.evidence['passed'] = False
        with self.assertRaisesRegex(ValueError, 'failed'):
            self.row()
        self.evidence['passed'] = True
        self.evidence['commands'] = [{'returncode': 1}]
        with self.assertRaisesRegex(ValueError, 'failed'):
            self.row()
        self.evidence['commands'] = []
        self.record['evidence_path'] = 'different.json'
        with self.assertRaisesRegex(ValueError, 'disagree'):
            self.row()

    def test_unknown_status_and_uncompleted_active_run_are_rejected(self):
        self.registry['experiments'][0]['status'] = 'maybe'
        with self.assertRaisesRegex(ValueError, 'status'):
            collect(ROOT, self.registry)
        self.registry['experiments'][0]['status'] = 'failed'
        with self.assertRaisesRegex(ValueError, 'Active experiment'):
            collect(ROOT, self.registry)

    def test_zero_measured_accuracy_is_not_missing(self):
        self.record['ground_truth_accuracy'] = {
            'status': 'measured', 'query_hit_at_5': 0.0, 'evaluated_query_count': 5}
        row = self.row()
        self.assertEqual(row['query_hit_at_5'], 0.0)
        self.assertEqual(row['quality_evaluated_queries'], 5)
        self.assertEqual(row['quality_reason'], '')
        self.record['ground_truth_accuracy']['evaluated_query_count'] = 0
        with self.assertRaisesRegex(ValueError, 'Hit@5'):
            self.row()

    def test_terminal_output_has_units_boundaries_rankings_and_no_fake_accuracy(self):
        output = terminal_table([self.row()])
        self.assertIn('285,146', output)
        self.assertIn('36.535 (9)', output)
        self.assertIn('Pending', output)
        self.assertIn('Fresh s (n)', output)
        result = terminal_results(ROOT, self.spec['experiment_id'])
        self.assertIn('Rank | Clip timestamp | Source seconds | Cosine score', result)
        self.assertIn('Reading saved results only', result)
        self.assertIn(self.evidence['retrieval_results'][0]['query'], result)
        for match in self.evidence['retrieval_results'][0]['results']:
            self.assertIn(f'{match["cosine_similarity"]:.6f}', result)
        with self.assertRaisesRegex(ValueError, 'No completed measurements'):
            terminal_results(ROOT, 'not_run')

    def test_invalid_sample_sets_are_rejected(self):
        for stats in ({'count': 2, 'samples': [1]},
                      {'count': 1, 'samples': [float('nan')]},
                      {'count': 1, 'samples': [float('inf')]},
                      {'count': 1, 'samples': [-1]}):
            with self.subTest(stats=stats), self.assertRaises(ValueError):
                summary_stats(stats)

    def test_metadata_only_generation_is_repeatable_and_preserves_inputs(self):
        # Only copy JSON: no videos, indexes, model cache or preview images exist.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            needed = {'experiments/registry.json', self.registry['update_rates']}
            for spec in self.registry['experiments']:
                needed.add(spec['evidence'])
                if spec.get('benchmark_record'):
                    needed.add(spec['benchmark_record'])
            needed.update(d['manifest'] for d in self.registry['datasets'])
            before = {}
            for name in needed:
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, dest)
                before[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, '.csv and .md'):
                generate(root, csv_path=self.spec['evidence'])
            generate(root)
            csv_path = root / 'experiments/summary.csv'
            report = root / 'docs/RESULTS_OVERVIEW.md'
            first = (csv_path.read_bytes(), report.read_bytes())
            generate(root)
            self.assertEqual(first, (csv_path.read_bytes(), report.read_bytes()))
            with csv_path.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), sum(s['status'] in ('current','completed')
                                          for s in self.registry['experiments']))
            self.assertEqual(rows[0]['index_bytes'], '285146')
            self.assertEqual(rows[0]['query_hit_at_5'], '')
            self.assertTrue(rows[0]['quality_reason'])
            self.assertIn('Pending annotations', report.read_text())
            self.assertEqual(before, {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                                      for name in needed})


if __name__ == '__main__':
    unittest.main()
