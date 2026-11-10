"""Apply explicit availability review, then write shared per-camera dataset manifests."""
import argparse,csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_search.availability import make_availability_report
from video_search.preprocessing import write_json,full_hash,load_config


def finalize(config_path,scan_path,decisions_path,clip_dir,output,manifest_suffix='.dataset.json'):
    config=load_config(config_path);scan=json.loads(Path(scan_path).read_text())
    decisions=json.loads(Path(decisions_path).read_text())
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    report=make_availability_report(scan,decisions)
    report['analysis_path']=str(Path(scan_path).resolve());report['analysis_sha256']=full_hash(scan_path)
    report['decisions_path']=str(Path(decisions_path).resolve());report['decisions_sha256']=full_hash(decisions_path)
    write_json(output/'availability.json',report)
    with (output/'intervals.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['camera_id','source_start_seconds','source_end_seconds_exclusive','duration_seconds','status'])
        for name,camera in report['cameras'].items():
            for item in camera['intervals']:
                writer.writerow([name,item['start'],item['end'],item['duration_seconds'],item['status']])
            write_json(output/f'{name}.availability.json',{'source_id':'nyc_traffic','source':report['source'],**camera})
    clips=Path(clip_dir);exports=json.loads((clips/'manifest.json').read_text())
    for camera in exports['cameras']:
        name=camera['id'];quality=report['cameras'][name]
        first,last=camera['first_retained_source_seconds'],camera['last_retained_source_seconds']
        issues=[i for i in quality['intervals'] if i['status']!='available_no_detected_issue'
                and i['start']<=last and i['end']>first]
        if issues:raise ValueError(f'Development interval has quality flags for {name}: {issues}')
        video=clips/camera['video'];mapping=clips/camera['timeline_csv']
        dataset={'schema_version':1,'dataset_id':'nyc_traffic_dev_000500_001500_v1','camera_id':name,
                 'camera_description':quality['description'],
                 'source_recording':{'id':'nyc_traffic',**config['source']},
                 'video':{'path':str(video.resolve()),'sha256':full_hash(video),
                          'metadata':camera['video_metadata']},
                 'timestamp_mapping':{'path':str(mapping.resolve()),'sha256':full_hash(mapping)},
                 'availability_report':{'path':str((output/'availability.json').resolve()),'sha256':full_hash(output/'availability.json')},
                 'availability_policy':'exclude_confirmed_unavailable_only',
                 'valid_source_intervals':quality['valid_source_intervals'],
                 'uncertain_source_intervals':quality['uncertain_intervals'],
                 'confirmed_unavailable_intervals':quality['confirmed_unavailable_intervals'],
                 'requested_source_interval':[exports['requested_start_seconds'],exports['requested_end_seconds_exclusive']],
                 'first_retained_source_seconds':first,'last_retained_source_seconds':last,
                 'crop':camera['crop'],'preprocessing':{'encoding':config['encoding'],'no_autorotate':True,
                 'temporal_resampling':False,'boundary_policy':exports['boundary_policy'],
                 'config_path':str(Path(config_path).resolve()),'config_sha256':full_hash(config_path),
                 'export_manifest_path':str((clips/'manifest.json').resolve()),'export_manifest_sha256':full_hash(clips/'manifest.json')}}
        path=clips/f'{name}{manifest_suffix}'
        if path.exists():raise FileExistsError(path)
        write_json(path,dataset)
    print('Availability reports and three dataset manifests saved:',output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default='configs/nyc_traffic.json');p.add_argument('--scan',required=True)
    p.add_argument('--decisions',required=True);p.add_argument('--clips',required=True);p.add_argument('--output',required=True)
    p.add_argument('--manifest-suffix', default='.dataset.json')
    a=p.parse_args();finalize(a.config,a.scan,a.decisions,a.clips,a.output,a.manifest_suffix)
