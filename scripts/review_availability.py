"""Extract source snapshots for candidate black intervals; decisions remain explicit."""
import argparse,csv,io,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageOps
from video_search.preprocessing import input_command,crop_filter,load_config,write_json


def review(config_path,scan_path,output):
    config=load_config(config_path);scan=json.loads(Path(scan_path).read_text())
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    records=[];images=[]
    cameras={c['id']:c for c in config['cameras']}
    for name,item in scan['cameras'].items():
        intervals=item['candidate_intervals']['black']
        if not intervals:continue
        times=[]
        with (Path(scan_path).parent/item['frame_metrics_csv']).open(newline='') as stream:
            times=[float(row['source_seconds']) for row in csv.DictReader(stream) if row['strict_black']=='1']
        for i,interval in enumerate(intervals):
            selected=[t for t in times if interval['start']<=t<interval['end']]
            if not selected:continue
            choices=sorted(set([selected[0],selected[len(selected)//2],selected[-1]]))
            files=[]
            for j,t in enumerate(choices):
                command=input_command(config,max(0,t-1))+['-loglevel','error','-vf',f'trim=start={t-1e-9:.12f},{crop_filter(cameras[name]["crop"])}',
                    '-frames:v','1','-f','image2pipe','-c:v','png','pipe:1']
                result=subprocess.run(command,capture_output=True)
                if result.returncode:raise ValueError(result.stderr.decode(errors='replace'))
                image=Image.open(io.BytesIO(result.stdout)).convert('RGB')
                path=output/f'{name}_black_{i}_{j}.png';image.save(path)
                files.append({'path':str(path),'source_seconds':t,'command':command})
                images.append((f'{name}:black:{i} @ {t:.6f}s',image.copy()))
            records.append({'candidate_id':f'{name}:black:{i}',**interval,'samples':files,'decision':'pending'})
    sheet=Image.new('RGB',(1080,max(1,(len(images)+2)//3)*260),'white');draw=ImageDraw.Draw(sheet)
    for i,(label,image) in enumerate(images):
        x,y=(i%3)*360,(i//3)*260;draw.text((x+4,y+4),label,fill='black')
        sheet.paste(ImageOps.contain(image,(350,228)),(x+4,y+26))
    sheet.save(output/'black_candidates.jpg',quality=95)
    write_json(output/'candidates.json',records)
    print(f'Saved {len(records)} candidate intervals and {len(images)} evidence snapshots: {output}')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default='configs/nyc_traffic.json');p.add_argument('--scan',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();review(a.config,a.scan,a.output)
