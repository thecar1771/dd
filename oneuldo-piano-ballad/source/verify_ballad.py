"""Independently compare the generated two-staff XML, MIDI and complete Korean lyric mapping."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
from omr.genres.contracts import Composition
from omr.piano_music.export import read_piano_xml_events

ap=argparse.ArgumentParser()
ap.add_argument('--root',type=Path,required=True)
ap.add_argument('--source',type=Path,required=True)
args=ap.parse_args()
sys.path.insert(0,str(args.source/'tests/genres'))
from test_arrangement import parse_midi

root=args.root
composition=Composition.from_dict(json.loads((root/'piano/composition.json').read_text(encoding='utf-8')))
assert composition.plan.genre=='ballad' and composition.plan.bpm==72 and composition.plan.bars==32
assert composition.plan.parts==('piano_rh','piano_lh')
expected=sorted((e.bar,e.onset,e.duration,e.pitch,e.part) for e in composition.events)
for kind in ('piano','piano-only'):
    text=(root/kind/'score.musicxml').read_text(encoding='utf-8')
    tree=ET.fromstring(text)
    assert len(tree.findall('part'))==1 and tree.findtext('part/measure/attributes/staves')=='2'
    assert len(tree.findall('part/measure'))==32
    assert sorted(read_piano_xml_events(text))==expected
    assert all(n.find('unpitched') is None for n in tree.findall('.//note'))
    fmt,tpq,tracks=parse_midi(root/kind/'score.mid')
    assert fmt==1 and all(t['end']==32*4*tpq and t['hanging']==0 for t in tracks)
    named={t['name']:t for t in tracks[1:]}
    assert set(named)=={'piano_rh','piano_lh'}
    for role in named:
        target=sorted((int((e.bar*4+e.onset)*tpq),int(e.duration*tpq),e.pitch,e.velocity) for e in composition.events if e.part==role)
        assert sorted((s,d,key,v) for s,d,key,ch,v in named[role]['notes'])==target
assert (root/'piano/score.mid').read_bytes()==(root/'piano-only/score.mid').read_bytes()
tree=ET.parse(root/'piano/score.musicxml').getroot()
lines=json.loads((root/'lyric-cues.json').read_text(encoding='utf-8'))
placements=json.loads((root/'lyric-placements.json').read_text(encoding='utf-8'))
assert len(lines)==12
expected_lyrics=''.join(line['text'].replace(' ','') for line in lines)
assert ''.join(n.text for n in tree.findall('.//lyric/text'))==expected_lyrics
assert len(tree.findall('.//lyric/text'))==len(placements)==len(expected_lyrics)
assert all(n.text=='single' for n in tree.findall('.//lyric/syllabic'))
assert all(abs(line['start_seconds']-line['bar']*240/72)<1e-6 for line in lines)
assert '오늘도 최선을 다할게요' in (root/'lyrics.txt').read_text(encoding='utf-8')
assert all(e.pitch is not None and not e.unpitched for e in composition.events)
audio=json.loads((root/'audio-verification.json').read_text(encoding='utf-8'))
assert audio['clipped_samples']==0
assert audio['mp3_sha256']==hashlib.sha256((root/'piano/piano.mp3').read_bytes()).hexdigest()
report=dict(bars=32,bpm=72,music_seconds=32*240/72,piano_notes=len(composition.events),
            lyric_lines=len(lines),lyric_syllables=len(expected_lyrics),
            melody_range=[min(e.pitch for e in composition.events if e.part=='piano_rh'),max(e.pitch for e in composition.events if e.part=='piano_rh')],
            exact_xml_notes_timing=True,exact_midi_notes_timing_velocity=True,
            complete_lyrics=True,korean_hyphen_display='single',no_hanging_notes=True,
            audio_scope='piano playing melody and accompaniment; no vocal audio',
            checkpoint_sha256=composition.metadata['checkpoint_sha256'])
(root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True))
