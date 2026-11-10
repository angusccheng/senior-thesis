"""Conservative availability labeling and source-time interval accounting."""
import unittest
from video_search.availability import Runs, complement, make_availability_report
from video_search.dataset import checked_intervals


class AvailabilityTests(unittest.TestCase):
    def test_run_boundaries_and_complement(self):
        run=Runs();run.update(True,2);run.update(True,5);run.update(False,7)
        run.update(True,9);run.finish(10)
        self.assertEqual(run.intervals,[[2,7],[9,10]])
        self.assertEqual(complement([[2,4],[3,5],[7,8]],0,10),[[0,2],[5,7],[8,10]])

    def test_only_reviewed_black_is_excluded(self):
        scan={'source':{},'source_seconds_end':100.,'source_seconds_start':0.,
              'cameras':{'cam':{'description':'test','candidate_intervals':{
                  'black':[{'start':10.,'end':30.,'duration':20.}],
                  'blank':[], 'frozen':[{'start':50.,'end':90.,'duration':40.}]}}}}
        pending=make_availability_report(scan,{})['cameras']['cam']
        self.assertEqual(pending['valid_source_intervals'],[[0,100.]])
        self.assertEqual(pending['confirmed_unavailable_seconds'],0)
        reviewed=make_availability_report(scan,{'cam:black:0':{'decision':'confirm_black_outage'}})['cameras']['cam']
        self.assertEqual(reviewed['valid_source_intervals'],[[0,10.],[30.,100.]])
        self.assertEqual(reviewed['total_usable_seconds'],40.)
        self.assertEqual(reviewed['uncertain_seconds'],40.)
        self.assertEqual(reviewed['confirmed_unavailable_seconds'],20.)
        self.assertEqual(reviewed['eligible_seconds_excluding_confirmed_outages'],80.)
        self.assertEqual(sum(i['duration_seconds'] for i in reviewed['intervals']),100.)

    def test_invalid_eligibility_intervals(self):
        for intervals in ([[1,0]], [[0,2],[1,3]], [[float('nan'),3]]):
            with self.assertRaises(ValueError):checked_intervals(intervals)

    def test_explicit_service_card_is_unavailable(self):
        scan={'source':{},'source_seconds_end':100.,'source_seconds_start':0.,
              'cameras':{'cam':{'candidate_intervals':{'black':[],'blank':[],'frozen':[]}}}}
        decisions={'cam:manual:service':{'decision':'confirm_service_unavailable','start':20,'end':30}}
        camera=make_availability_report(scan,decisions)['cameras']['cam']
        self.assertEqual(camera['confirmed_unavailable_intervals'],[[20,30]])
        self.assertEqual(camera['total_usable_seconds'],90)
        self.assertEqual(camera['intervals'][1]['status'],'confirmed_unavailable_service')

if __name__=='__main__':unittest.main()
