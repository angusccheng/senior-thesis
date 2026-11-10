"""Run an OpenCLIP sampling experiment with guarded fresh-process queries and metrics."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import resource
import shlex
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['HF_HUB_OFFLINE']='1'

QUERIES=[
    'Pedestrians crossing a wide crosswalk at a busy city intersection.',
    'Yellow taxis driving through an intersection.',
    'A bus passing through a crowded intersection.',
]


def worker(operation, metrics_path, original, arguments):
    from unittest.mock import patch
    from contextlib import ExitStack
    import builtins
    import cv2
    import main
    from video_search.encoder import OpenCLIPEncoder
    began=perf_counter()
    sys.argv=['main.py',*arguments]
    with ExitStack() as stack:
        if operation=='search':
            source=Path(original).resolve()
            def guarded_open(original_open):
                def opened(file,*args,**kwargs):
                    if isinstance(file,(str,bytes,os.PathLike)) and Path(os.fsdecode(file)).resolve()==source:
                        raise AssertionError('Original grid recording accessed during retrieval')
                    return original_open(file,*args,**kwargs)
                return opened
            stack.enter_context(patch('builtins.open',guarded_open(builtins.open)))
            stack.enter_context(patch('io.open',guarded_open(io.open)))
            original_capture=cv2.VideoCapture
            def capture(path,*args,**kwargs):
                if isinstance(path,(str,os.PathLike)) and Path(path).resolve()==source:
                    raise AssertionError('Original grid decoded during retrieval')
                return original_capture(path,*args,**kwargs)
            stack.enter_context(patch.object(cv2,'VideoCapture',capture))
            stack.enter_context(patch.object(OpenCLIPEncoder,'encode_images',side_effect=AssertionError('Image embeddings recomputed during retrieval')))
            stack.enter_context(patch.object(main,'build_index',side_effect=AssertionError('Index rebuilt during retrieval')))
            original_popen=subprocess.Popen
            def popen(command,*args,**kwargs):
                parts=shlex.split(command) if isinstance(command,str) else [str(p) for p in command]
                if (parts and Path(parts[0]).name in ('ffmpeg','avconv')) or str(source) in parts:
                    raise AssertionError('External original-video processing or reencoding during retrieval')
                return original_popen(command,*args,**kwargs)
            stack.enter_context(patch('subprocess.Popen',popen))
        main.main()
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    Path(metrics_path).write_text(json.dumps({'operation_seconds_excluding_imports':perf_counter()-began,
        'peak_rss_bytes':int(rss if sys.platform=='darwin' else rss*1024),
        'rss_method':'resource.getrusage(RUSAGE_SELF).ru_maxrss; Darwin bytes, Linux KiB converted to bytes',
        'retrieval_guards':operation=='search'},indent=2)+'\n')


def experiment(manifest_path,index_path,result_root,output,interval=5.0,batch_size=16,threads=4,queries=None,method="uniform",max_frames=None):
    import hashlib
    import numpy as np
    from PIL import Image
    from video_search.dataset import DatasetContext
    from video_search.encoder import OpenCLIPEncoder
    from video_search.pipeline import load_index,sha256_file
    from video_search.video import scan_video,selected_frames,FrameInfo
    from video_search.benchmarking import capture_hardware, baseline_record
    queries = list(QUERIES if queries is None else queries)
    if not queries or any(not isinstance(q,str) or not q.strip() for q in queries):
        raise ValueError('At least one nonempty query is required')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads(Path(manifest_path).read_text());video=manifest['video']['path']
    original=manifest['source_recording']['path']
    index_path=Path(index_path);result_root=Path(result_root)
    if index_path.exists() or result_root.exists():raise FileExistsError('Choose fresh index/results paths')
    commands=[]
    report={'queries':queries,'commands':commands,'checks':{},'dataset_manifest':str(manifest_path)}
    report['benchmark_schema_version']=1
    report['hardware_at_run_start']=capture_hardware(inference_device='cpu')
    def save():
        (output/'experiment.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'queries.json').write_text(json.dumps({'queries':[{'id':f'q{i}','text':q} for i,q in enumerate(queries,1)],'ground_truth':None},indent=2)+'\n')
    def execute(operation,args,tag):
        metrics=output/f'{tag}.metrics.json'
        command=[sys.executable,'scripts/run_development_experiment.py','--worker',operation,
            '--metrics',str(metrics),'--original-source',original,'--',*map(str,args)]
        began=perf_counter();result=subprocess.run(command,cwd=ROOT,env={**os.environ,'HF_HUB_OFFLINE':'1'},capture_output=True,text=True)
        seconds=perf_counter()-began
        record={'command':'HF_HUB_OFFLINE=1 '+shlex.join(command),'wall_seconds':seconds,
                'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        commands.append(record);save()
        (output/f'{tag}.stdout.txt').write_text(result.stdout)
        (output/f'{tag}.stderr.txt').write_text(result.stderr)
        if result.returncode:raise RuntimeError(record)
        record['metrics']=json.loads(metrics.read_text());save()
        print(f'{tag}: {seconds:.3f} s; peak RSS {record["metrics"]["peak_rss_bytes"]:,} bytes',flush=True)
        return record
    method_args=['--method',method]
    if method=='diversity':method_args+=['--max-frames',str(max_frames)]
    indexing=execute('index',['index','--video',video,'--interval',str(interval),'--batch-size',str(batch_size),
        '--threads',str(threads),'--dataset-manifest',manifest_path,'--index',index_path,*method_args],'index')
    e,t,n,metadata=load_index(index_path)
    initial_hash=sha256_file(index_path)
    report['index_metadata']=json.loads(index_path.with_suffix('.metadata.json').read_text())
    report['index_sha256']=initial_hash
    ctx=DatasetContext(manifest_path,video,sha256_file(video))
    timeline=scan_video(video)
    times=np.array([f.seconds for f in timeline])
    if method=='uniform':
        targets=np.arange(0,times[-1]+1e-9,interval)
        positions=np.unique(np.searchsorted(times+1e-9,targets,side='left'))
        expected=[timeline[i] for i in positions if i<len(timeline) and ctx.eligible(timeline[i])]
        if n.tolist()!=[f.number for f in expected]:raise AssertionError('Uniform selection mismatch')
        report['checks']['uniform_selection_matches_independent_grid']=True
    else:
        # Eligibility/count/source mapping checked here; independent feature
        # selection is checked below after loading the verification encoder.
        expected=[frame for frame in timeline if frame.number in set(n.tolist())]
        if len(n)!=min(max_frames,sum(ctx.eligible(f) for f in timeline)):
            raise AssertionError('Diversity retained-frame budget mismatch')
        if not all(ctx.eligible(f) for f in expected):raise AssertionError('Ineligible frame retained')
        report['checks']['diversity_budget_and_eligibility']=True
    report['checks']['finite_unit_embeddings']=bool(np.isfinite(e).all() and np.allclose(np.linalg.norm(e,axis=1),1,atol=1e-5))
    with np.load(index_path,allow_pickle=False) as archive:source_times=archive['source_timestamps']
    if not np.allclose(source_times,ctx.timestamps(expected),atol=1e-9):raise AssertionError('Stored source-time mapping mismatch')
    results=[];query_times=[]
    for i,q in enumerate(queries,1):
        folder=result_root/f'query_{i:02d}'
        record=execute('search',['search','--query',q,'--index',index_path,'--threads',str(threads),'--output',folder],f'query_{i:02d}')
        query_times.append(record['wall_seconds'])
        data=json.loads((folder/'results.json').read_text());results.append(data)
        repeated=result_root/f'query_{i:02d}_repeat'
        execute('search',['search','--query',q,'--index',index_path,'--threads',str(threads),'--output',repeated],f'query_{i:02d}_repeat')
        other=json.loads((repeated/'results.json').read_text())
        if data['results']!=other['results']:raise AssertionError('Repeated fresh-process query mismatch')
        if len(data['results'])!=min(5,len(e)):raise AssertionError('Expected top five')
    report['checks']['fresh_process_queries_repeat_identically']=True
    report['checks']['original_not_accessed_no_reencoding_no_image_embedding_recompute']=True
    # Independent cosine and image verification occurs after guarded retrieval.
    encoder=OpenCLIPEncoder(threads=threads)
    if method=='diversity':
        candidates=[f for f in timeline if ctx.eligible(f)]
        features=[];images=[]
        for _,rgb in selected_frames(video,candidates):
            images.append(Image.fromarray(rgb))
            if len(images)==batch_size:
                features.append(encoder.encode_images(images));images=[]
        if images:features.append(encoder.encode_images(images))
        candidate_embeddings=np.concatenate(features)
        vectors=candidate_embeddings.astype(np.float64)
        closest=np.full(len(vectors),np.inf);picked=[];remaining=np.ones(len(vectors),dtype=bool)
        current=0
        for _ in range(min(max_frames,len(vectors))):
            picked.append(current);remaining[current]=False
            # Elementwise reduction rather than the selector's matrix-vector product.
            distances=np.clip(1-np.sum(vectors*vectors[current],axis=1),0,2)
            closest=np.minimum(closest,distances)
            current=int(np.argmax(np.where(remaining,closest,-np.inf)))
        positions=np.array(sorted(picked))
        if n.tolist()!=[candidates[i].number for i in positions]:
            raise AssertionError('Independent diversity selection mismatch')
        if not np.array_equal(e,candidate_embeddings[positions]):
            raise AssertionError('Retained embeddings differ from independently encoded candidates')
        report['checks']['independent_diversity_selection_and_embeddings']=True
    all_rows=[r for result in results for r in result['results']]
    wanted={r['frame_number']:FrameInfo(r['frame_number'],r['seconds']) for r in all_rows}
    jpeg={}
    for info,rgb in selected_frames(video,list(wanted.values())):
        buffer=io.BytesIO();Image.fromarray(rgb).save(buffer,format='JPEG',quality=95);jpeg[info.number]=buffer.getvalue()
    maximum_error=0.
    for i,result in enumerate(results,1):
        q=encoder.encode_text(result['query']).astype(np.float64);vectors=e.astype(np.float64)
        cosine=np.sum(vectors*q,axis=1)/(np.linalg.norm(vectors,axis=1)*np.linalg.norm(q))
        order=np.argsort(-cosine,kind='stable')[:5]
        if [r['frame_number'] for r in result['results']]!=n[order].tolist():raise AssertionError('Independent cosine ordering mismatch')
        for row,j in zip(result['results'],order):
            maximum_error=max(maximum_error,abs(row['cosine_similarity']-cosine[j]))
            if abs(row['source_seconds']-source_times[j])>1e-9:raise AssertionError('Retrieval source-time mismatch')
            for suffix in ('','_repeat'):
                if (result_root/f'query_{i:02d}{suffix}'/row['image']).read_bytes()!=jpeg[row['frame_number']]:
                    raise AssertionError('Preview JPEG/frame mismatch')
    if maximum_error>1e-6:raise AssertionError('Cosine error too large')
    report['checks']['independent_cosine_and_rankings']=True
    report['checks']['all_preview_jpegs_match_cropped_frame']=True
    report['checks']['retrieval_source_times_match_export_csv']=True
    report['checks']['index_unchanged']=sha256_file(index_path)==initial_hash
    report['maximum_cosine_error']=maximum_error
    report['retrieval_results']=results
    # Resident latency is separate from fresh CLI startup and preview extraction.
    from video_search.pipeline import search_index
    encoder.metadata()
    search_index(index_path,queries[0],encoder)  # one untimed warm-up
    resident=[]
    for _ in range(3):
        for query in queries:
            started=perf_counter();search_index(index_path,query,encoder);resident.append(perf_counter()-started)
    report['performance']={'indexing_fresh_process_seconds':indexing['wall_seconds'],
        'index_peak_rss_bytes':indexing['metrics']['peak_rss_bytes'],'query_fresh_process_seconds':query_times,
        'average_query_fresh_process_seconds':float(np.mean(query_times)),
        'query_peak_rss_bytes':[c['metrics']['peak_rss_bytes'] for c in commands if 'metrics' in c and c['metrics']['retrieval_guards']],
        'index_bytes':index_path.stat().st_size,'frames':len(e),'embedding_dimension':e.shape[1],
        'numeric_payload_bytes':metadata['storage']['payload_bytes'],
        'resident_query_seconds':resident,
        'average_resident_query_seconds':float(np.mean(resident)),
        'resident_timing_scope':f'Loaded model, one untimed warm-up, {3*len(queries)} queries; includes NPZ loading and text encoding/ranking, excludes previews/model load/initial fingerprint.',
        'conditions':f'CPU, {threads} Torch threads, fp32, seed0, batch{batch_size}, {method} selection (interval={interval if method=="uniform" else None}, max_frames={max_frames}), cached weights, offline; fresh-query times include imports/model loading/cropped-preview decoding/JPEG/CSV/JSON writes. Original grid is inaccessible during retrieval.'}
    benchmark=baseline_record(report,index_path,output/'experiment.json')
    (output/'benchmark_record.json').write_text(json.dumps(benchmark,indent=2,allow_nan=False)+'\n')
    report['passed']=all(report['checks'].values());save()
    print(json.dumps(report['performance'],indent=2),flush=True)


if __name__=='__main__':
    if '--worker' in sys.argv:
        separator=sys.argv.index('--');head=sys.argv[1:separator];tail=sys.argv[separator+1:]
        p=argparse.ArgumentParser();p.add_argument('--worker',choices=['index','search']);p.add_argument('--metrics',required=True);p.add_argument('--original-source',required=True)
        a=p.parse_args(head);worker(a.worker,a.metrics,a.original_source,tail)
    else:
        p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset-manifest',required=True);p.add_argument('--index',required=True);p.add_argument('--results',required=True);p.add_argument('--output',required=True)
        p.add_argument('--method',choices=['uniform','diversity'],default='uniform')
        p.add_argument('--max-frames',type=int)
        p.add_argument('--interval',type=float,default=5.0)
        p.add_argument('--batch-size',type=int,default=16)
        p.add_argument('--threads',type=int,default=4)
        p.add_argument('--queries',type=Path,help='JSON with queries: [{id, text}]')
        a=p.parse_args()
        import math
        if not math.isfinite(a.interval) or a.interval<=0 or a.batch_size<=0 or a.threads<=0:
            p.error('interval, batch size and threads must be positive; interval must be finite')
        if a.method=='diversity' and (a.max_frames is None or a.max_frames<=0):
            p.error('diversity requires positive --max-frames')
        queries=None if a.queries is None else [q['text'] for q in json.loads(a.queries.read_text())['queries']]
        experiment(a.dataset_manifest,a.index,a.results,a.output,a.interval,a.batch_size,a.threads,queries,a.method,a.max_frames)
