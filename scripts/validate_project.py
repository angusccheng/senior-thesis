"""Validate regression commands, migration integrity and source preservation."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_search.preprocessing import load_config,sampled_fingerprint


def validate(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    evidence={'commands':[],'checks':{}}
    commands=[['-m','unittest','discover','-s','tests','-v'],['-m','pip','check'],['main.py','--help'],['prepare_data.py','--help']]
    for i,args in enumerate(commands):
        command=[sys.executable,*args]
        result=subprocess.run(command,capture_output=True,text=True,env={**os.environ,'HF_HUB_OFFLINE':'1'})
        (output/f'command_{i}.stdout.txt').write_text(result.stdout);(output/f'command_{i}.stderr.txt').write_text(result.stderr)
        evidence['commands'].append({'command':command,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        if result.returncode:raise AssertionError(evidence['commands'][-1])
    inventory=json.loads(Path('experiments/cleanup_2026-11-03.json').read_text())
    for row in inventory['legacy_files_preserved']:
        path=Path(row['path'])
        if path.stat().st_size!=row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise AssertionError(f'Legacy artifact changed: {path}')
    evidence['checks']['all_legacy_files_preserved_by_sha256']=len(inventory['legacy_files_preserved'])
    old=json.loads(Path('archive/pre_cleanup_2026-11-03/configs/nyc_traffic.json').read_text())
    config=load_config('configs/nyc_traffic.json')
    evidence['checks']['crop_coordinates_unchanged']=([c['crop'] for c in old['cameras']]==[c['crop'] for c in config['cameras']])
    source=Path(config['source']['path'])
    evidence['checks']['original_recording_unchanged']=(source.stat().st_size==old['source']['size_bytes']
        and source.stat().st_mtime_ns==old['source']['mtime_ns']
        and sampled_fingerprint(source)==old['source']['sampled_sha256'])
    evidence['checks']['compatibility_output_link']=Path('output').is_symlink() and Path('output').resolve()==Path('archive/legacy_output').resolve()
    import numpy as np
    payloads=[]
    for version in (1,2,3):
        path=Path(f'indexes/nyc_dev_uniform_5s_v{version}/index.npz')
        with np.load(path,allow_pickle=False) as archive:
            payloads.append([archive[k] for k in ('embeddings','timestamps','frame_numbers','source_timestamps')])
    evidence['checks']['all_three_index_builds_have_identical_numeric_payloads']=all(np.array_equal(a,b) for payload in payloads[1:] for a,b in zip(payloads[0],payload))
    evidence['checks']['tests_and_existing_cli_help_passed']=True
    evidence['passed']=all(bool(v) for v in evidence['checks'].values())
    if not evidence['passed']:raise AssertionError(evidence)
    (output/'validation.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence['checks'],indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args();validate(a.output)
