"""Streaming per-camera availability evidence; uncertain content is never discarded."""
import csv
from collections import deque
from pathlib import Path
import queue
import subprocess
import threading
from time import perf_counter

import numpy as np

from .preprocessing import ShowInfo, crop_filter, load_config, write_json, full_hash


class Runs:
    def __init__(self):
        self.start = None
        self.intervals = []

    def update(self, active, timestamp, start=None):
        if active and self.start is None:
            self.start = timestamp if start is None else start
        if not active and self.start is not None:
            if timestamp > self.start:
                self.intervals.append([self.start, timestamp])
            self.start = None

    def finish(self, end):
        self.update(False, end)


def mosaic_command(config, width=80, height=48):
    cameras = config['cameras']
    filters = [f'[0:v:0]split={len(cameras)}' + ''.join(f'[in{i}]' for i in range(len(cameras)))]
    for i, camera in enumerate(cameras):
        x,y,w,h = camera['crop']
        if camera.get('diagnostic_roi'):
            rx,ry,w,h = camera['diagnostic_roi'];x+=rx;y+=ry
        filters.append(f'[in{i}]{crop_filter([x,y,w,h])},scale={width}:{height}:flags=area,format=gray[c{i}]')
    filters.append(''.join(f'[c{i}]' for i in range(len(cameras))) + f'hstack=inputs={len(cameras)},showinfo,setpts=PTS-STARTPTS[out]')
    return ['ffmpeg','-hide_banner','-nostdin','-nostats','-copyts','-start_at_zero',
            '-noautorotate','-threads','4','-i',config['source']['path'],
            '-filter_complex_threads','1','-filter_complex',';'.join(filters),
            '-map','[out]','-an','-c:v','rawvideo','-threads','1',
            '-enc_time_base:v','filter','-fps_mode','passthrough','-f','rawvideo','pipe:1']


def stream_mosaics(command, size):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    messages, stop = queue.Queue(maxsize=128), threading.Event()
    tail = deque(maxlen=30)
    def send(value):
        while not stop.is_set():
            try:
                messages.put(value,timeout=.1);return
            except queue.Full:
                pass
    def drain():
        parser = ShowInfo()
        try:
            for raw in process.stderr:
                line=raw.decode(errors='replace');tail.append(line)
                item=parser.parse(line)
                if item is not None:send(item)
        except Exception as error:
            send(error)
        finally:
            send(None)
    reader=threading.Thread(target=drain,daemon=True);reader.start()
    try:
        frame=0
        while True:
            raw=process.stdout.read(size)
            if not raw:break
            if len(raw)!=size:raise ValueError('Truncated availability mosaic')
            item=messages.get(timeout=60)
            if item is None or isinstance(item,Exception) or item[0]!=frame:
                raise ValueError(f'Mosaic/timestamp mismatch: {item}')
            yield float(item[1]),raw
            frame+=1
        if process.wait()!=0:raise ValueError('FFmpeg availability scan failed:\n'+''.join(tail))
    finally:
        stop.set()
        if process.poll() is None:process.terminate();process.wait()
        reader.join(timeout=5);process.stdout.close();process.stderr.close()


def analyze(config_path, output):
    """Decode original once; no full-size camera videos are exported."""
    config=load_config(config_path)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    command=mosaic_command(config)
    cameras=config['cameras'];width,height=80,48
    stats={c['id']:{'camera':c,'frames':0,'updates':0,'exact_repeats':0,'near_unchanged_pairs':0,
                     'black':Runs(),'blank':Runs(),'frozen':Runs(),'black_frames':0,
                     'previous':None,'last_timestamp':None,'last_update':None,
                     'active_updates':0,'active_pair_seconds':0.,'active_pairs':0,
                     'active_unchanged_pairs':0,'active_exact_repeats':0,'previous_black':False}
           for c in cameras}
    streams={c['id']:(output/f'{c["id"]}.frames.csv').open('w',newline='') for c in cameras}
    writers={name:csv.writer(stream) for name,stream in streams.items()}
    for writer in writers.values():writer.writerow(['frame','source_seconds','mean_luma','std_luma','dark_fraction','mad','changed_fraction','observable_update','exact_repeat','near_unchanged','strict_black','uniform_blank'])
    began=perf_counter();count=0;first=None;last=None
    try:
        for timestamp,raw in stream_mosaics(command,width*height*len(cameras)):
            if last is not None and timestamp<=last:raise ValueError('Non-increasing source PTS')
            if first is None:first=timestamp
            mosaic=np.frombuffer(raw,dtype=np.uint8).reshape(height,width*len(cameras))
            for i,camera in enumerate(cameras):
                name=camera['id'];s=stats[name];image=mosaic[:,i*width:(i+1)*width]
                mean,std=float(image.mean()),float(image.std())
                dark=float(np.mean(image<=12))
                black=mean<=4 and std<=1.5 and dark>=.999
                blank=std<=2 and not black
                mad,fraction,changed,exact,unchanged=0.,0.,False,False,False
                if s['previous'] is not None:
                    delta=np.abs(image.astype(np.int16)-s['previous'].astype(np.int16))
                    mad=float(delta.mean());fraction=float(np.mean(delta>=8))
                    changed=mad>=2 and fraction>=.01
                    exact=not delta.any();unchanged=mad<=.15 and fraction<=.001
                    s['exact_repeats']+=int(exact);s['near_unchanged_pairs']+=int(unchanged)
                    s['updates']+=int(changed)
                    if not black and not s['previous_black']:
                        s['active_updates']+=int(changed);s['active_pair_seconds']+=timestamp-s['last_timestamp']
                        s['active_pairs']+=1;s['active_unchanged_pairs']+=int(unchanged);s['active_exact_repeats']+=int(exact)
                s['black'].update(black,timestamp)
                s['blank'].update(blank,timestamp)
                s['frozen'].update(unchanged and not black and not blank,timestamp,start=s['last_timestamp'])
                s['black_frames']+=int(black);s['frames']+=1
                writers[name].writerow([count,f'{timestamp:.12f}',mean,std,dark,mad,fraction,int(changed),int(exact),int(unchanged),int(black),int(blank)])
                s['previous']=image.copy();s['last_timestamp']=timestamp;s['previous_black']=black
            count+=1;last=timestamp
            if count%2000==0:print(f'Analyzed {count} stored frames; source {timestamp/3600:.2f} h; elapsed {perf_counter()-began:.1f} s',flush=True)
    finally:
        for stream in streams.values():stream.close()
    if count<2:raise ValueError('Insufficient source frames')
    expected=config['source']['metadata']['ffprobe']['streams'][0].get('nb_frames')
    if expected and count!=int(expected):raise ValueError(f'Decoded {count}, expected {expected} frames')
    end=config['source']['metadata']['video_end_seconds'];span=last-first
    result={'schema_version':1,'source':config['source'],'configuration_path':str(Path(config_path).resolve()),
            'configuration_sha256':full_hash(config_path),'command':command,
            'ffmpeg_version':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
            'source_seconds_start':first,'source_seconds_end':end,'last_source_frame_seconds':last,
            'decoded_frames':count,'observed_stored_frame_rate':(count-1)/span,
            'analysis_seconds':perf_counter()-began,'analysis_resolution_per_camera':[width,height],
            'thresholds':{'strict_black':'mean<=4,std<=1.5,>=99.9% pixels<=12','blank':'std<=2, not strict black',
                          'observable_update':'MAD>=2 and >=1% pixels change by >=8',
                          'near_unchanged':'MAD<=0.15 and <=0.1% pixels change by >=8',
                          'freeze_review_min_seconds':90,'black_confirmation_min_seconds':10},
            'limitations':['Content-change proxy, not sensor/network FPS.','Static/dark/frozen candidates need review.','Transitions are stored-presentation times, not network failure instants.'],
            'cameras':{}}
    for name,s in stats.items():
        for kind in ('black','blank','frozen'):s[kind].finish(end)
        intervals={kind:[{'start':a,'end':b,'duration':b-a} for a,b in s[kind].intervals
                         if kind=='black' or b-a>=(90 if kind=='frozen' else 10)]
                   for kind in ('black','blank','frozen')}
        pairs=s['frames']-1
        result['cameras'][name]={'description':s['camera']['description'],'crop':s['camera']['crop'],'diagnostic_roi':s['camera']['diagnostic_roi'],
            'frames':s['frames'],'observable_updates':s['updates'],'observable_update_hz':s['updates']/span,
            'exact_repeated_pair_fraction':s['exact_repeats']/pairs,'near_unchanged_pair_fraction':s['near_unchanged_pairs']/pairs,
            'strict_black_frame_fraction':s['black_frames']/s['frames'],
            'nonblack_observable_update_hz':s['active_updates']/s['active_pair_seconds'] if s['active_pair_seconds'] else None,
            'nonblack_near_unchanged_pair_fraction':s['active_unchanged_pairs']/s['active_pairs'] if s['active_pairs'] else None,
            'nonblack_exact_repeated_pair_fraction':s['active_exact_repeats']/s['active_pairs'] if s['active_pairs'] else None,
            'nonblack_pair_seconds':s['active_pair_seconds'],'candidate_intervals':intervals,
            'frame_metrics_csv':f'{name}.frames.csv'}
    write_json(output/'scan.json',result)
    print(f'Scan complete: {count} frames, {result["analysis_seconds"]:.1f} s; {output}/scan.json',flush=True)
    return result


def merged_ranges(values):
    result=[]
    for start,end in sorted(values):
        if result and start<=result[-1][1]+1e-8:result[-1][1]=max(result[-1][1],end)
        else:result.append([start,end])
    return result


def complement(values, start, end):
    result=[];position=start
    for a,b in merged_ranges(values):
        a=max(start,a);b=min(end,b)
        if b<=position:continue
        if a>position:result.append([position,a])
        position=max(position,b)
    if position<end:result.append([position,end])
    return result


def make_availability_report(scan, decisions):
    """Use explicit visual-review decisions to confirm black outages; freeze stays uncertain."""
    end=scan['source_seconds_end'];start=0.
    report={'schema_version':1,'source':scan['source'],'source_id':'nyc_traffic',
            'timeline':'source seconds relative to format.start_time; stored-frame/held-frame evidence',
            'source_duration_seconds':end,'default_indexing_policy':'exclude_confirmed_unavailable_only',
            'review_decisions':decisions,'cameras':{},
            'limitations':['A frame class holds until the next stored presentation time.',
                           'Actual network failure/recovery can occur between observations.',
                           'Unflagged imagery is not a ground-truth guarantee of availability.',
                           'Frozen/blank/dark candidates are preserved for manual review.']}
    for name,camera in scan['cameras'].items():
        flags=[]
        for i,interval in enumerate(camera['candidate_intervals']['black']):
            key=f'{name}:black:{i}'
            decision=decisions.get(key,{})
            status='confirmed_unavailable_black' if decision.get('decision')=='confirm_black_outage' else 'uncertain_black'
            flags.append({**interval,'status':status,'candidate_id':key,'evidence':decision})
        for key,decision in decisions.items():
            if key.startswith(name+':manual:') and decision.get('decision') in ('confirm_black_outage', 'confirm_service_unavailable'):
                a,b=decision['start'],decision['end']
                if not 0<=a<b<=end:raise ValueError('Manual review interval outside source timeline')
                status = 'confirmed_unavailable_service' if decision['decision']=='confirm_service_unavailable' else 'confirmed_unavailable_black'
                flags.append({'start':a,'end':b,'duration':b-a,'status':status,
                              'candidate_id':key,'evidence':decision})
        for kind in ('blank','frozen'):
            for i,interval in enumerate(camera['candidate_intervals'][kind]):
                flags.append({**interval,'status':f'uncertain_{kind}','candidate_id':f'{name}:{kind}:{i}'})
        if scan['source_seconds_start']>0:
            flags.append({'start':0,'end':scan['source_seconds_start'],'status':'uncertain_unobserved'})
        priority={'confirmed_unavailable_black':0,'confirmed_unavailable_service':0,'uncertain_unobserved':1,'uncertain_black':2,'uncertain_blank':3,'uncertain_frozen':4}
        edges=sorted({start,end,*[v for flag in flags for v in (flag['start'],flag['end'])]})
        intervals=[]
        for a,b in zip(edges,edges[1:]):
            active=[f for f in flags if f['start']<=a+1e-9 and f['end']>=b-1e-9]
            selected=min(active,key=lambda f:priority[f['status']]) if active else None
            status=selected['status'] if selected else 'available_no_detected_issue'
            evidence_ids=sorted(f['candidate_id'] for f in active if 'candidate_id' in f)
            if intervals and intervals[-1]['status']==status and intervals[-1]['candidate_ids']==evidence_ids:
                intervals[-1]['end']=b;intervals[-1]['duration_seconds']=b-intervals[-1]['start']
            else:intervals.append({'start':a,'end':b,'duration_seconds':b-a,'status':status,'candidate_ids':evidence_ids})
        confirmed=merged_ranges([[f['start'],f['end']] for f in flags if f['status'].startswith('confirmed_unavailable')])
        uncertain=merged_ranges([[i['start'],i['end']] for i in intervals if i['status'].startswith('uncertain')])
        unflagged=merged_ranges([[i['start'],i['end']] for i in intervals if i['status']=='available_no_detected_issue'])
        eligible=complement(confirmed,start,end)
        report['cameras'][name]={**{k:v for k,v in camera.items() if k!='candidate_intervals'},
            'intervals':intervals,'evidence_candidates':flags,'confirmed_unavailable_intervals':confirmed,
            'uncertain_intervals':uncertain,'unflagged_intervals':unflagged,'valid_source_intervals':eligible,
            'total_usable_seconds':sum(b-a for a,b in unflagged),
            'usable_duration_definition':'Conservative unflagged duration, excluding both confirmed outages and uncertain intervals; not annotated ground truth.',
            'eligible_seconds_excluding_confirmed_outages':sum(b-a for a,b in eligible),
            'confirmed_unavailable_seconds':sum(b-a for a,b in confirmed),
            'uncertain_seconds':sum(b-a for a,b in uncertain)}
    return report
