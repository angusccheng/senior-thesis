"""Experiment orchestration: isolated outputs, explicit settings, honest registration."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from video_search.experiments import command, load_catalog, output_paths, run, status, validate_inputs

ROOT = Path(__file__).resolve().parents[1]


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.spec = copy.deepcopy(load_catalog(ROOT)['experiments'][1])

    def setup_inputs(self, root):
        for field in ('footage', 'queries', 'dataset_manifest'):
            target = root / self.spec[field]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('unused synthetic file' if field == 'footage' else '{}')
        (root / self.spec['dataset_manifest']).write_text(json.dumps({
            'video': {'path': str(root / self.spec['footage'])}}))
        (root / self.spec['queries']).write_text(json.dumps({
            'queries': [{'id': 'q1', 'text': 'A truck.'}]}))
        registry = root / 'experiments/registry.json'
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({'schema_version': 1, 'active_experiment_id': 'old',
                                        'experiments': []}))

    def test_catalog_rejects_unsafe_duplicate_ids_and_unimplemented_methods(self):
        catalog = load_catalog(ROOT)
        for field, value in [('experiment_id', '../escape'), ('method', 'change_aware'),
                             ('interval_seconds', float('nan')), ('interval_seconds', 0),
                             ('threads', True), ('batch_size', -1)]:
            bad = copy.deepcopy(catalog)
            bad['experiments'][0][field] = value
            with tempfile.TemporaryDirectory() as temp:
                Path(temp, 'catalog.json').write_text(json.dumps(bad))
                with self.subTest(field=field), self.assertRaises(ValueError):
                    load_catalog(temp, 'catalog.json')
        catalog['experiments'].append(copy.deepcopy(catalog['experiments'][0]))
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, 'catalog.json').write_text(json.dumps(catalog))
            with self.assertRaises(ValueError):
                load_catalog(temp, 'catalog.json')

    def test_commands_use_explicit_parameters_and_consistent_output_ids(self):
        self.spec.update(interval_seconds=10, threads=2, batch_size=8)
        args = command(self.spec, python='test-python')
        for flag, expected in [('--interval', '10'), ('--threads', '2'),
                               ('--batch-size', '8'), ('--queries', self.spec['queries'])]:
            self.assertEqual(args[args.index(flag)+1], expected)
        self.assertEqual(args[0], 'test-python')
        for path in output_paths(self.spec).values():
            self.assertIn(self.spec['experiment_id'], path)

    def test_inputs_must_match_video_and_queries_must_be_nonempty(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.setup_inputs(root)
            validate_inputs(root, self.spec)
            manifest = root / self.spec['dataset_manifest']
            manifest.write_text(json.dumps({'video': {'path': 'another.mp4'}}))
            with self.assertRaisesRegex(ValueError, 'does not match'):
                validate_inputs(root, self.spec)
            self.setup_inputs(root)
            (root / self.spec['queries']).write_text('{"queries": [{"id": "q1", "text": " "}]}')
            with self.assertRaisesRegex(ValueError, 'nonempty'):
                validate_inputs(root, self.spec)

    def test_registered_and_partial_runs_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.setup_inputs(root)
            path = root / output_paths(self.spec)['index']
            path.parent.mkdir(parents=True)
            self.assertIn('incomplete', status(root, self.spec))
            with patch('video_search.experiments.subprocess.run') as execute:
                with self.assertRaises(FileExistsError):
                    run(root, self.spec)
                execute.assert_not_called()
        with patch('video_search.experiments.subprocess.run') as execute:
            existing = load_catalog(ROOT)['experiments'][0]
            with self.assertRaisesRegex(FileExistsError, 'already registered'):
                run(ROOT, existing)
            execute.assert_not_called()

    def test_saved_run_status_does_not_hide_changed_configuration(self):
        existing = copy.deepcopy(load_catalog(ROOT)['experiments'][0])
        self.assertEqual(status(ROOT, existing), 'current')
        existing['interval_seconds'] = 10
        self.assertIn('configuration differs', status(ROOT, existing))

    def test_failed_process_keeps_config_and_does_not_register(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.setup_inputs(root)
            registry = root / 'experiments/registry.json'
            before = registry.read_bytes()
            def fail(args, **kwargs):
                (root / output_paths(self.spec)['evidence']).mkdir(parents=True)
                return subprocess.CompletedProcess(args, 1)
            with patch('video_search.experiments.subprocess.run', side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, 'failed'):
                    run(root, self.spec)
            self.assertEqual(before, registry.read_bytes())
            snapshot = root / output_paths(self.spec)['evidence'] / 'run_config.json'
            self.assertEqual(json.loads(snapshot.read_text())['returncode'], 1)

    def test_success_registers_once_and_refreshes_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.setup_inputs(root)
            def succeed(args, **kwargs):
                folder = root / output_paths(self.spec)['evidence']
                folder.mkdir(parents=True)
                (folder / 'experiment.json').write_text('{"passed": true}')
                (folder / 'benchmark_record.json').write_text('{}')
                return subprocess.CompletedProcess(args, 0)
            with patch('video_search.experiments.subprocess.run', side_effect=succeed), \
                 patch('video_search.reporting.experiment_row') as validate, \
                 patch('video_search.reporting.generate') as refresh, \
                 patch('video_search.reporting.terminal_results', return_value='Saved stats/results') as display:
                run(root, self.spec)
                validate.assert_called_once()
                refresh.assert_called_once_with(root)
                display.assert_called_once_with(root, self.spec['experiment_id'])
            registry = json.loads((root / 'experiments/registry.json').read_text())
            self.assertEqual(registry['active_experiment_id'], 'old')
            self.assertEqual(len(registry['experiments']), 1)
            self.assertEqual(registry['experiments'][0]['status'], 'completed')
            self.assertEqual(registry['experiments'][0]['experiment_id'], self.spec['experiment_id'])


if __name__ == '__main__':
    unittest.main()
