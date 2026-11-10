"""Summarize visual changes separately from stored FPS and confirmed outages."""
import argparse,csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_search.preprocessing import write_json


def summarize(scan_path,availability_path,output):
    if Path(output).exists():raise FileExistsError(f'Choose a new rate-summary path: {output}')
    scan=json.loads(Path(scan_path).read_text());availability=json.loads(Path(availability_path).read_text())
    result={'analysis_resolution':[80,48],'thresholds':scan['thresholds'],
            'stored_frame_count':scan['decoded_frames'],'stored_fps':scan['observed_stored_frame_rate'],
            'notes':'Pair counts/fractions are frame-pair weighted; Hz divides events by eligible inter-frame elapsed time. These are visible-change proxies, not camera/network FPS. Confirmed outages excluded only in eligible_nonoutage; frozen candidates remain flagged.',
            'cameras':{}}
    for name,camera in scan['cameras'].items():
        ranges=availability['cameras'][name]['valid_source_intervals']
        groups={key:{'pairs':0,'updates':0,'exact_duplicates':0,'near_unchanged':0,'pair_seconds':0.} for key in ('full_recording','eligible_nonoutage','development_300_900')}
        previous=None
        with (Path(scan_path).parent/camera['frame_metrics_csv']).open(newline='') as stream:
            for row in csv.DictReader(stream):
                timestamp=float(row['source_seconds'])
                if previous is not None:
                    eligible=any(a-1e-9<=previous<timestamp<b-1e-9 for a,b in ranges)
                    selected=['full_recording']
                    if eligible:selected.append('eligible_nonoutage')
                    if 300<=previous<timestamp<900:selected.append('development_300_900')
                    for key in selected:
                        group=groups[key];group['pairs']+=1;group['pair_seconds']+=timestamp-previous
                        group['updates']+=int(row['observable_update']);group['exact_duplicates']+=int(row['exact_repeat'])
                        group['near_unchanged']+=int(row['near_unchanged'])
                previous=timestamp
        for group in groups.values():
            n=group['pairs'];span=group['pair_seconds']
            group['observable_change_hz']=group['updates']/span if span else None
            group['stored_pair_rate']=n/span if span else None
            group['exact_duplicate_pair_fraction']=group['exact_duplicates']/n if n else None
            group['near_unchanged_pair_fraction']=group['near_unchanged']/n if n else None
        result['cameras'][name]=groups
    write_json(output,result)
    print('Saved',output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scan',required=True);p.add_argument('--availability',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();summarize(a.scan,a.availability,a.output)
