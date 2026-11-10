"""Create source-image evidence for uncertain intervals without excluding them."""
import argparse,csv,io,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageOps
from video_search.preprocessing import load_config,input_command,crop_filter,write_json


def extract(config_path,scan_path,availability_path,output):
    config=load_config(config_path);scan=json.loads(Path(scan_path).read_text())
    availability=json.loads(Path(availability_path).read_text());output=Path(output)
    output.mkdir(parents=True,exist_ok=False);records=[];pictures=[]
    camera_settings={c['id']:c for c in config['cameras']}
    for name,report in availability['cameras'].items():
        if not report['uncertain_intervals']:continue
        with (Path(scan_path).parent/scan['cameras'][name]['frame_metrics_csv']).open(newline='') as stream:
            times=[float(row['source_seconds']) for row in csv.DictReader(stream)]
        for i,(start,end) in enumerate(report['uncertain_intervals']):
            available=[t for t in times if start-1e-9<=t<end-1e-9]
            selected=sorted(set([available[0],available[len(available)//2],available[-1]]))
            images=[]
            for j,t in enumerate(selected):
                command=input_command(config,max(0,t-1))+['-loglevel','error','-vf',f'trim=start={t-1e-9:.12f},{crop_filter(camera_settings[name]["crop"])}',
                    '-frames:v','1','-f','image2pipe','-c:v','png','pipe:1']
                result=subprocess.run(command,capture_output=True,check=True)
                image=Image.open(io.BytesIO(result.stdout)).convert('RGB')
                path=output/f'{name}_uncertain_{i}_{j}.png';image.save(path)
                images.append({'path':str(path),'source_seconds':t,'command':command});pictures.append((f'{name} @ {t:.6f}s',image.copy()))
            records.append({'camera_id':name,'start':start,'end':end,'status':'uncertain_frozen',
                            'decision':'manual_review_required_do_not_auto_exclude','images':images})
    sheet=Image.new('RGB',(1080,max(1,(len(pictures)+2)//3)*260),'white');draw=ImageDraw.Draw(sheet)
    for i,(label,image) in enumerate(pictures):
        x,y=(i%3)*360,(i//3)*260;draw.text((x+4,y+4),label,fill='black');sheet.paste(ImageOps.contain(image,(350,228)),(x+4,y+26))
    sheet.save(output/'uncertain_candidates.jpg',quality=95);write_json(output/'review_required.json',records)
    print(f'Saved {len(records)} uncertain intervals with source snapshots; no exclusions changed.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default='configs/nyc_traffic.json');p.add_argument('--scan',required=True);p.add_argument('--availability',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();extract(a.config,a.scan,a.availability,a.output)
