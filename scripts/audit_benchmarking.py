"""Audit saved baseline measurements; no model load, video decoding or benchmark rerun."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_search.benchmarking import baseline_record,capture_hardware


def audit(experiment,index,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    experiment=Path(experiment);data=json.loads(experiment.read_text())
    record=baseline_record(data,index,experiment)
    record['audit_created_at_utc']=datetime.now(timezone.utc).isoformat()
    record['audit_did_not_rerun_index_or_queries']=True
    record['current_hardware_audit_only_not_historical']=capture_hardware(data['index_metadata']['encoder']['device'])
    (output/'benchmark_record.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print('Saved',output/'benchmark_record.json')
    print('Fresh-process query median:',record['timing']['fresh_process_query_with_previews_seconds']['median'])
    print('Warm-query median:',record['timing']['resident_query_without_previews_seconds']['median'])
    print('p95 withheld: insufficient samples. Missing historical measurements remain unavailable.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment',default='experiments/nyc_dev_uniform_5s_v3/experiment.json')
    p.add_argument('--index',default='indexes/nyc_dev_uniform_5s_v3/index.npz')
    p.add_argument('--output',required=True)
    a=p.parse_args();audit(a.experiment,a.index,a.output)
