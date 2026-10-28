"""Independent event/lyric/MIDI verification for this concrete rap sample."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

from omr.genres.contracts import Composition
from omr.genres.export import RAP_GUIDE_KEY
from omr.piano_music.export import read_piano_xml_events

ap=argparse.ArgumentParser()
ap.add_argument('--root',type=Path,required=True)
ap.add_argument('--source',type=Path,required=True)
args=ap.parse_args()
sys.path.insert(0,str(args.source/'tests/genres'))
from test_arrangement import parse_xml,parse_midi,event_key

root=args.root
c=Composition.from_dict(json.loads((root/'rap/composition.json').read_text(encoding='utf-8')))
p=Composition.from_dict(json.loads((root/'piano/composition.json').read_text(encoding='utf-8')))
assert c.plan.bpm==96 and c.plan.bars==32 and p.plan.parts==('piano_rh','piano_lh')
tree=ET.parse(root/'rap/score.musicxml').getroot()
assert len(tree.findall('part'))==2
piano=deepcopy(tree)
piano.find('part-list').remove(piano.find('part-list/score-part'))
piano.remove(piano.find('part'))
expected=sorted((e.bar,e.onset,e.duration,e.pitch,e.part) for e in p.events)
assert sorted(read_piano_xml_events(ET.tostring(piano,encoding='unicode')))==expected
assert sorted(read_piano_xml_events((root/'piano/score.musicxml').read_text(encoding='utf-8')))==expected
rap=deepcopy(tree)
rap.find('part-list').remove(rap.findall('part-list/score-part')[1])
rap.remove(rap.findall('part')[1])
rap.find('part-list/score-part/part-name').text='vocal'
parsed,parts=parse_xml(ET.tostring(rap,encoding='unicode'))
actual,measures=parts['vocal']
assert len(measures)==32 and all(d==4 for voices in measures for d in voices.values())
assert sorted(map(event_key,actual))==sorted(event_key(e) for e in c.events if e.part=='vocal')
lines=json.loads((root/'lyric-cues.json').read_text(encoding='utf-8'))
expected_lyrics=''.join(line['text'].replace(' ','') for line in lines)
assert ''.join(n.text for n in tree.findall('.//lyric/text'))==expected_lyrics
assert all(n.text=='single' for n in tree.findall('.//lyric/syllabic'))
assert len(expected_lyrics)==271 and len(lines)==24
assert [line['start_seconds'] for line in lines]==[e*2.5 for e in list(range(4,16))+list(range(16,28))]
for kind,composition in [('piano',p),('rap',c)]:
    fmt,tpq,tracks=parse_midi(root/kind/'score.mid')
    assert fmt==1 and all(t['end']==32*4*tpq and t['hanging']==0 for t in tracks)
    named={t['name']:t for t in tracks[1:]}
    for role in ('piano_rh','piano_lh'):
        expected_notes=sorted((int((e.bar*4+e.onset)*tpq),int(e.duration*tpq),e.pitch,e.velocity) for e in composition.events if e.part==role)
        assert sorted((s,d,key,v) for s,d,key,ch,v in named[role]['notes'])==expected_notes
    if kind=='rap':
        guide=next(t for t in tracks if 'rap rhythm guide' in t['name'])
        expected_guide=sorted((int((e.bar*4+e.onset)*tpq),int(e.duration*tpq),RAP_GUIDE_KEY,e.velocity) for e in c.events if e.part=='vocal')
        assert sorted((s,d,key,v) for s,d,key,ch,v in guide['notes'])==expected_guide
    else:
        assert set(named)=={'piano_rh','piano_lh'}
report=dict(bars=32,bpm=96,music_seconds=80,piano_notes=len(p.events),rap_syllables=271,lyric_lines=24,
            exact_rap_xml_timing=True,exact_grand_staff_xml_timing=True,exact_midi_notes_timing_velocity=True,
            complete_lyrics=True,korean_syllabic_single=True,no_hanging_notes=True,
            audio_scope='piano backing only; optional rap rhythm MIDI is a woodblock timing guide, not human vocals',
            checkpoint_sha256=c.metadata['checkpoint_sha256'])
(root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True))
