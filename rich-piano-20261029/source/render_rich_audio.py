"""Master a piano-only performance using the official Salamander bank."""
from array import array
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import wave

midi,out,assets=map(Path,sys.argv[1:4])
if out.exists() and any(out.iterdir()):raise FileExistsError(out)
out.mkdir(parents=True,exist_ok=True)
bank=json.loads((assets/'provenance.json').read_text())
sf2=Path(bank['soundfont'])
render=subprocess.run([str(assets/'rich_piano_render'),str(sf2),str(midi),str(out/'dry-float.wav')],capture_output=True,text=True,check=True)
native=json.loads(render.stdout)
room='aecho=0.8:0.88:41|67:0.10|0.06'
analysis=subprocess.run(['ffmpeg','-hide_banner','-i',str(out/'dry-float.wav'),'-af',room+',loudnorm=I=-19:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
measured=json.loads(re.findall(r'\{[^{}]+\}',analysis.stderr)[-1])
normal=('loudnorm=I=-19:TP=-1.5:LRA=11:measured_I='+measured['input_i']+
        ':measured_LRA='+measured['input_lra']+':measured_TP='+measured['input_tp']+
        ':measured_thresh='+measured['input_thresh']+':offset='+measured['target_offset']+
        ':linear=true:print_format=json')
master=subprocess.run(['ffmpeg','-hide_banner','-n','-i',str(out/'dry-float.wav'),'-af',room+','+normal,
                       '-ar','44100','-ac','2','-c:a','pcm_s16le',str(out/'piano.wav')],capture_output=True,text=True,check=True)
master_stats=json.loads(re.findall(r'\{[^{}]+\}',master.stderr)[-1])
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-n','-i',str(out/'piano.wav'),'-c:a','libmp3lame','-q:a','2',str(out/'piano.mp3')],check=True)
with wave.open(str(out/'piano.wav'),'rb') as stream:
    rate,channels,width,frames=stream.getframerate(),stream.getnchannels(),stream.getsampwidth(),stream.getnframes()
    data=array('h',stream.readframes(frames))
assert (rate,channels,width)==(44100,2,2)
if sys.byteorder!='little':data.byteswap()
peak=max(map(abs,data));rms=math.sqrt(sum(v*v for v in data)/len(data))
assert peak<32760 and rms>0
report=dict(seconds=frames/rate,sample_rate=rate,channels=channels,clipped_samples=sum(abs(v)>=32767 for v in data),
    peak_dbfs=20*math.log10(peak/32768),rms_dbfs=20*math.log10(rms/32768),
    mp3_sha256=hashlib.sha256((out/'piano.mp3').read_bytes()).hexdigest(),
    performance_sha256=hashlib.sha256(midi.read_bytes()).hexdigest(),soundfont=bank,native_render=native,
    master_filter=room+','+normal,loudness_analysis=measured,master_loudness=master_stats,
    scope='one acoustic piano only; separate expressive MIDI, small room effect, loudness matched; technical checks, not subjective preference')
(out/'audio-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('loudness_analysis','master_loudness','master_filter')}),flush=True)
