"""Measurement boundaries and honest missing-data/storage/statistics semantics."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from video_search.benchmarking import StageTimings, latency_summary, storage_inventory, capture_hardware, unavailable


class BenchmarkingTests(unittest.TestCase):
    def test_latency_small_sample_does_not_claim_tail_or_variability(self):
        stats=latency_summary([1,4,2,3])
        self.assertEqual(stats['median'],2.5)
        self.assertIsNone(stats['p95'])
        self.assertIn('Fewer',stats['p95_reason'])
        self.assertIsNone(latency_summary([1])['sample_stddev'])
        self.assertEqual(latency_summary([])['summary']['status'],'unavailable')
        for bad in ([float('nan')],[float('inf')],[-1]):
            with self.assertRaises(ValueError):latency_summary(bad)

    def test_nearest_rank_p95_only_with_sufficient_samples(self):
        self.assertEqual(latency_summary(range(100))['p95'],94)
        self.assertIsNone(latency_summary(range(99))['p95'])

    def test_decoder_timing_excludes_consumer_work(self):
        now=[0.]
        timing=StageTimings(clock=lambda:now[0])
        def decode():
            for i in range(2):
                now[0]+=2
                yield i
        values=[]
        for value in timing.iterate('decode',decode()):
            values.append(value)
            now[0]+=100  # simulated inference happens in the consumer
        self.assertEqual(values,[0,1])
        self.assertEqual(timing.seconds['decode'],4)
        self.assertEqual(timing.calls['decode'],3)  # includes terminal next()/cleanup

    def test_stage_exceptions_cleanup_and_nested_stages_rejected(self):
        timing=StageTimings()
        with self.assertRaises(ValueError):
            with timing.measure('outer'):
                with timing.measure('inner'):
                    pass
        self.assertIsNone(timing.active)
        self.assertIn('outer',timing.snapshot())

    def test_storage_budget_counts_only_required_files_and_no_fake_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            index=Path(temp)/'index';index.write_bytes(b'123')
            report=Path(temp)/'report';report.write_bytes(b'12345')
            result=storage_inventory([{'path':str(index),'role':'retrieval_required'},
                                      {'path':str(report),'role':'experiment_metadata'}])
            self.assertEqual(result['primary_index_bytes'],3)
            self.assertEqual(result['measured_bytes_by_role']['experiment_metadata'],5)
            self.assertIsNone(result['measured_bytes_by_role']['shared_model'])
            with self.assertRaises(ValueError):
                storage_inventory([{'path':str(index),'role':'retrieval_required'},
                                   {'path':str(index),'role':'experiment_metadata'}])
            missing=storage_inventory([{'path':str(Path(temp)/'missing'),'role':'retrieval_required'}])
            self.assertIsNone(missing['primary_index_bytes'])
            self.assertEqual(missing['primary_status'],'unavailable')

    def test_hardware_permission_failures_remain_unavailable(self):
        with patch('video_search.benchmarking.sys.platform','darwin'), \
             patch('video_search.benchmarking._sysctl',return_value=unavailable('permission denied')):
            result=capture_hardware()
        self.assertIsNone(result['cpu_model']['value'])
        self.assertEqual(result['physical_ram_bytes']['status'],'unavailable')
        self.assertIn('CPU',result['accelerator_peak_memory']['reason'])


if __name__=='__main__':unittest.main()
