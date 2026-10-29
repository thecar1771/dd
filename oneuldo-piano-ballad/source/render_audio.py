"""Render the exact piano MIDI and inspect audio; no vocal or subjective quality claim."""
from array import array
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tarfile
import wave

root, assets = map(Path, sys.argv[1:3])
sf2=assets/'audio-tools/font/usr/share/sounds/sf2/TimGM6mb.sf2'
wav=root/'piano/piano.wav'
mp3=root/'piano/piano.mp3'
subprocess.run([str(assets/'audio-tools/piano_render'),str(sf2),str(root/'piano/score.mid'),str(wav)],check=True)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-n','-i',str(wav),'-codec:a','libmp3lame','-q:a','3',str(mp3)],check=True)
with wave.open(str(wav),'rb') as stream:
    rate,channels,width,frames=stream.getframerate(),stream.getnchannels(),stream.getsampwidth(),stream.getnframes()
    assert (rate,channels,width)==(44100,2,2)
    data=array('h',stream.readframes(frames))
if sys.byteorder!='little':data.byteswap()
peak=max(map(abs,data));rms=math.sqrt(sum(v*v for v in data)/len(data))
assert abs(frames/rate-(32*240/72+3))<.15
assert 0<peak<32760 and rms>0
report=dict(seconds=frames/rate,sample_rate=rate,channels=channels,peak_dbfs=round(20*math.log10(peak/32768),3),
            rms_dbfs=round(20*math.log10(rms/32768),3),clipped_samples=sum(abs(v)>=32767 for v in data),
            mp3_sha256=hashlib.sha256(mp3.read_bytes()).hexdigest(),
            soundfont_sha256=hashlib.sha256(sf2.read_bytes()).hexdigest(),
            synthesis='TinySoundFont + TimGM6mb acoustic grand piano',
            scope='piano melody and accompaniment only; no sung voice; technical verification, not a listening score')
(root/'audio-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(root/'piano/piano.lrc').write_bytes((root/'lyrics.lrc').read_bytes())
archive=assets/'workday-ballad-20261029.tgz'
with tarfile.open(archive,'w:gz') as tar:
    for file in sorted(root.rglob('*')):
        if file.is_file() and file.suffix!='.wav':tar.add(file,arcname='sample/'+file.relative_to(root).as_posix())
print(json.dumps(dict(audio=report,archive=str(archive))),flush=True)
