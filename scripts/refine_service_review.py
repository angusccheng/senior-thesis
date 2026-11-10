"""Refine an explicitly observed service card using full-scan metrics and source snapshots."""
import csv,io,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageOps,ImageDraw
from video_search.preprocessing import load_config,input_command,crop_filter,write_json

config=load_config('configs/nyc_traffic.json')
base=Path('data/metadata/nyc_traffic/availability_scan_v1')
name='central_park_72nd_post37';camera=next(c for c in config['cameras'] if c['id']==name)
with (base/f'{name}.frames.csv').open(newline='') as stream:rows=list(csv.DictReader(stream))
reference=min(rows,key=lambda r:abs(float(r['source_seconds'])-9317))
mean,std=float(reference['mean_luma']),float(reference['std_luma'])
matching=[i for i,r in enumerate(rows) if abs(float(r['mean_luma'])-mean)<2 and abs(float(r['std_luma'])-std)<2 and float(r['dark_fraction'])<.001]
if not matching or matching!=list(range(matching[0],matching[-1]+1)):
    raise ValueError('Service-metric match is not one contiguous interval; manual refinement required')
start=float(rows[matching[0]]['source_seconds']);end=float(rows[matching[-1]+1]['source_seconds'])
output=base/'service_review';output.mkdir(exist_ok=False)
images=[];evidence=[]
indices=[matching[0]-1,matching[0],matching[len(matching)//2],matching[-1],matching[-1]+1]
for j,i in enumerate(indices):
    t=float(rows[i]['source_seconds'])
    command=input_command(config,max(0,t-1))+['-loglevel','error','-vf',f'trim=start={t-1e-9:.12f},{crop_filter(camera["crop"])}','-frames:v','1','-f','image2pipe','-c:v','png','pipe:1']
    result=subprocess.run(command,capture_output=True,check=True)
    image=Image.open(io.BytesIO(result.stdout)).convert('RGB');path=output/f'service_{j}.png';image.save(path)
    images.append((t,image.copy()));evidence.append({'source_seconds':t,'path':str(path),'command':command})
sheet=Image.new('RGB',(1080,520),'white');draw=ImageDraw.Draw(sheet)
for i,(t,image) in enumerate(images):
    x,y=(i%3)*360,(i//3)*260;draw.text((x+4,y+4),f'{name} @ {t:.6f}s',fill='black');sheet.paste(ImageOps.contain(image,(350,228)),(x+4,y+26))
sheet.save(output/'service_transition.jpg',quality=95)
write_json(output/'service_candidate.json',{'camera_id':name,'start':start,'end':end,
    'metric_reference':reference,'matching_frames':len(matching),'matching_rule':'mean/std each within 2 of reference, dark fraction <0.001; candidate only until visual review',
    'evidence':evidence})
print('Service-card candidate:',start,end,len(matching),'frames;',output/'service_transition.jpg')
