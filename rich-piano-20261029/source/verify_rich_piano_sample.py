"""Independent MIDI event and concrete two-hand arrangement checks."""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
import mido

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from omr.genres.contracts import Composition


def features(composition):
    events=composition.events
    boundaries=sorted({e.bar*4+e.onset for e in events}|{e.bar*4+e.onset+e.duration for e in events})
    max_poly=0;spans=Counter();layered=F(0)
    for start,end in zip(boundaries,boundaries[1:]):
        active=[e for e in events if e.bar*4+e.onset<=start<e.bar*4+e.onset+e.duration]
        max_poly=max(max_poly,len(active))
        if len(active)>=3:layered+=end-start
        for hand in ('piano_lh','piano_rh'):
            pitches=[e.pitch for e in active if e.part==hand]
            span=max(pitches)-min(pitches) if pitches else 0
            spans[hand]=max(spans[hand],span)
    rhythms={tuple(sorted((str(e.onset),str(e.duration)) for e in events if e.bar==b and e.part=='piano_lh')) for b in range(composition.plan.bars)}
    counts={}
    for section in composition.plan.sections:
        key=section.role+'@'+str(section.start_bar+1)
        counts[key]=sum(section.start_bar<=e.bar<section.start_bar+section.bars for e in events)/section.bars
    return dict(notes=len(events),max_simultaneous_keys=max_poly,max_active_hand_span_semitones=dict(spans),
                beats_with_at_least_three_notes=float(layered),distinct_left_hand_rhythms=len(rhythms),
                notes_per_bar_by_section=counts)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--sample',type=Path,required=True);ap.add_argument('--baseline',type=Path,required=True)
    args=ap.parse_args()
    load=lambda p:Composition.from_dict(json.loads(p.read_text(encoding='utf-8')))
    current=load(args.sample/'piano/composition.json');old=load(args.baseline/'piano/composition.json')
    assert current.plan.parts==old.plan.parts and set(e.part for e in current.events)=={'piano_rh','piano_lh'}
    lead=Counter((e.bar,e.onset,e.duration,e.pitch) for e in old.events if e.part=='piano_rh')
    assert not lead-Counter((e.bar,e.onset,e.duration,e.pitch) for e in current.events if e.part=='piano_rh')
    expected=Counter((e.bar*4+e.onset,e.duration,e.pitch,e.velocity) for e in current.events)
    reports=[]
    for folder in ('piano','piano-only'):
        midi=mido.MidiFile(args.sample/folder/'score.mid');absolute=0;held={};actual=Counter();programs=set();tempos=[]
        for message in mido.merge_tracks(midi.tracks):
            absolute+=message.time
            if message.type=='program_change':programs.add(message.program)
            if message.type=='set_tempo':tempos.append(message.tempo)
            if message.type not in ('note_on','note_off'):continue
            key=(message.channel,message.note)
            if message.type=='note_on' and message.velocity:
                assert key not in held,('overlapping physical MIDI key',key)
                held[key]=(absolute,message.velocity)
            else:
                assert key in held,('unmatched note off',key)
                start,velocity=held.pop(key)
                actual[(F(start,midi.ticks_per_beat),F(absolute-start,midi.ticks_per_beat),message.note,velocity)]+=1
        assert not held and actual==expected and programs=={0}
        assert tempos==[60000000//current.plan.bpm]
        root=ET.parse(args.sample/folder/'score.musicxml').getroot()
        assert len(root.findall('part'))==1 and root.findtext('part/measure/attributes/staves')=='2'
        lyrics=[n.text for n in root.findall('.//lyric/text')]
        if folder=='piano':
            placements=json.loads((args.sample/'lyric-placements.json').read_text(encoding='utf-8'))
            assert ''.join(lyrics)==''.join(p['lyric'] for p in placements) and len(lyrics)==94
            assert all(n.text=='single' for n in root.findall('.//lyric/syllabic'))
        else:assert not lyrics
        reports.append(dict(folder=folder,midi_exact_note_match=True,piano_program_only=True,lyrics=len(lyrics)))
    # Physical keys across the two MIDI channels still belong to one piano.
    by_pitch=defaultdict(list)
    for e in current.events:by_pitch[e.pitch].append((e.bar*4+e.onset,e.bar*4+e.onset+e.duration))
    for pitch,intervals in by_pitch.items():
        intervals.sort()
        assert all(a[1]<=b[0] for a,b in zip(intervals,intervals[1:])),('same piano key across hands',pitch)
    new_features=features(current);old_features=features(old)
    assert all(v<=12 for v in new_features['max_active_hand_span_semitones'].values())
    assert new_features['max_simultaneous_keys']>old_features['max_simultaneous_keys']
    report=dict(checks=reports,original_lead_pitch_rhythm_preserved=True,baseline=old_features,rich=new_features,
                checkpoint_sha256=current.metadata['checkpoint_sha256'],
                score_sha256=hashlib.sha256((args.sample/'piano/score.mid').read_bytes()).hexdigest(),
                limits='Mechanical key-span/timing checks; not a human performance or listening preference evaluation.')
    (args.sample/'score-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
