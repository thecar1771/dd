"""Original office-life piano ballad using the existing joint-piano checkpoint."""
import argparse
from collections import defaultdict
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import torch
from omr.genres.contracts import Chord, Composition, ScoreEvent, Section, SongPlan
from omr.genres.export import write_midi
from omr.genres.lyrics import _syllable_marks
from omr.piano_music.export import piano_musicxml, read_piano_xml_events
from omr.piano_music.train import load_checkpoint

TITLE, BPM, SEED = '오늘도, 나의 자리', 72, 2026102903
LINES = [
    ('Verse', 4, '무거운 눈을 뜨고'), ('Verse', 6, '익숙한 길을 걸어'),
    ('Verse', 8, '책상 위 켜진 불빛'), ('Verse', 10, '나를 다시 깨우네'),
    ('Pre-Chorus', 12, '지친 마음 한켠에도'), ('Pre-Chorus', 14, '작은 숨이 이어져'),
    ('Chorus', 16, '오늘도 나의 자리에서'), ('Chorus', 18, '살아 있음을 느껴요'),
    ('Chorus', 20, '서툴러도 괜찮아요'), ('Chorus', 22, '내 하루를 다할게요'),
    ('Final Hook', 24, '오늘도 최선을 다할게요'), ('Final Hook', 26, '내일의 나를 만나러'),
]
PATTERNS = {7:[2,1,1,2,2,2,4], 8:[2,1,1,2,2,2,2,2],
            9:[1,1,2,1,1,2,2,2,2], 10:[1,1,2,1,1,2,1,1,2,2]}


def lyric_slots():
    slots, lines = defaultdict(list), []
    for section, bar, text in LINES:
        marks = _syllable_marks(text)
        assert len(marks) in PATTERNS, (text, len(marks))
        units = 0
        for i, ((syllable, syllabic), duration) in enumerate(zip(marks, PATTERNS[len(marks)])):
            absolute = units * 6
            b, onset = bar + absolute // 48, absolute % 48
            assert onset + duration * 6 <= 48
            slots[b].append(dict(onset=onset, duration=duration*6, hand='rh', lyric=syllable,
                                 syllabic=syllabic, line_index=i, line_length=len(marks)))
            units += duration
        assert units == 14
        lines.append(dict(section=section, bar=bar, start_seconds=bar*240/BPM,
                          end_seconds=(bar+2)*240/BPM, text=text))
    return slots, lines


@torch.inference_mode()
def sampled_bar(model, tok, history, chord, bar, melody_slots, previous):
    device = next(model.parameters()).device
    rng = torch.Generator(device=device).manual_seed(SEED + bar*104729)
    prefix = tok.prefix('major', 'romantic')
    current = [tok.ids['BAR'], tok.ids['LEN_48']]
    sampled, notes, placements = 0, [], []
    chorus = 16 <= bar < 28
    quiet = bar < 4 or bar >= 28
    pcs = {(chord.root + i) % 12 for i in (0, 3 if chord.quality == 'minor' else 4, 7)}
    bass = 36 + chord.root
    if chord.root in (0, 2):
        bass += 12
    # Authored quarter-note broken chords leave the right hand a clear lead line.
    slots = [dict(onset=i*12, duration=12, hand='lh', fixed=p)
             for i,p in enumerate([bass, bass+7, bass+(3 if chord.quality=='minor' else 4), bass+7])]
    if quiet:
        slots = [dict(onset=0, duration=24, hand='lh', fixed=bass),
                 dict(onset=24, duration=24, hand='lh', fixed=bass+7)]
    if melody_slots:
        slots += melody_slots
    else:
        slots += [dict(onset=12,duration=12,hand='rh'), dict(onset=24,duration=24,hand='rh')]

    def choose(candidates):
        nonlocal sampled
        if len(candidates)==1:
            return candidates[0]
        kept = list(history)
        while len(prefix)+sum(map(len, kept))+len(current)>model.config.max_sequence_length:
            kept.pop(0)
        x = prefix+[t for b in kept for t in b]+current
        logits = model(torch.tensor([x],device=device))[0,-1].float()
        ids = torch.tensor(candidates,device=device)
        probs = torch.softmax(logits[ids]/.68,dim=-1)
        assert torch.isfinite(probs).all()
        sampled += 1
        return ids[torch.multinomial(probs,1,generator=rng)].item()

    for slot in sorted(slots,key=lambda s:(s['onset'],s['hand']=='rh')):
        o,d,hand = slot['onset'],slot['duration'],slot['hand']
        current += [tok.ids[f'POS_{o}'],tok.ids[f'DUR_{d}']]
        if hand=='lh':
            pitches=[slot['fixed']]
        else:
            low,high = (67,79) if chorus else (64,76) if 12<=bar<16 else (60,72)
            tonal = pcs if o in (0,24) or slot.get('line_index')==slot.get('line_length',0)-1 else {0,2,4,5,7,9,11}
            pitches=[p for p in range(low,high+1) if p%12 in tonal]
            if previous:
                close=[p for p in pitches if abs(p-previous[-1])<=5]
                if close:
                    pitches=close
                if len(previous)>=2 and previous[-1]==previous[-2] and len(pitches)>1:
                    pitches=[p for p in pitches if p!=previous[-1]]
            if 'line_index' in slot:
                phase=slot['line_index']/max(1,slot['line_length']-1)
                center=(70 if chorus else 65)+round(4*(1-abs(2*phase-1)))
                shaped=[p for p in pitches if abs(p-center)<=5]
                if shaped:
                    pitches=shaped
        token=choose([tok.ids[f'PITCH_{p}'] for p in pitches])
        current.append(token)
        pitch=int(tok.tokens[token].split('_')[-1])
        bins=range(6,8) if hand=='lh' and chorus else range(5,7) if hand=='lh' else range(10,12) if chorus else range(7,9) if quiet else range(8,10)
        velocity_token=choose([tok.ids[f'VELOCITY_{v}'] for v in bins])
        current.append(velocity_token)
        velocity=tok.decode_velocity(int(tok.tokens[velocity_token].split('_')[-1]))
        notes.append([o,d,pitch,velocity])
        if hand=='rh':
            previous.append(pitch)
        if 'lyric' in slot:
            placements.append(dict(bar=bar,onset=o,duration=d,pitch=pitch,
                                   lyric=slot['lyric'],syllabic=slot['syllabic']))
    current.append(tok.ids['END_BAR'])
    row=dict(length=48,meter=[4,4],notes=sorted(notes,key=lambda n:(n[0],n[2])))
    return row,tok.encode_bar(row),placements,dict(bar=bar,sampled_choices=sampled)


def add_lyrics(root, placements):
    expected={(p['bar'],p['onset'],p['pitch']):p for p in placements}
    assigned=set()
    steps=dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)
    divisions=1
    for bar,measure in enumerate(root.find('part').findall('measure')):
        divisions=int(measure.findtext('attributes/divisions') or divisions)
        cursor,chord_start=F(0),F(0)
        for node in measure:
            if node.tag in ('backup','forward'):
                cursor += (-1 if node.tag=='backup' else 1)*F(int(node.findtext('duration')),divisions)
            elif node.tag=='note':
                duration=F(int(node.findtext('duration')),divisions)
                is_chord=node.find('chord') is not None
                onset=chord_start if is_chord else cursor
                if not is_chord:
                    chord_start=cursor
                    cursor+=duration
                p=node.find('pitch')
                if p is None or node.findtext('staff')!='1':
                    continue
                pitch=(int(p.findtext('octave'))+1)*12+steps[p.findtext('step')]+int(p.findtext('alter') or 0)
                key=(bar,int(onset*12),pitch)
                if key in expected:
                    assert key not in assigned
                    lyric=ET.SubElement(node,'lyric',number='1')
                    ET.SubElement(lyric,'syllabic').text='single'
                    ET.SubElement(lyric,'text').text=expected[key]['lyric']
                    assigned.add(key)
    assert assigned==set(expected)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--checkpoint',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--image-sha256',required=True)
    args=ap.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError('preserve earlier sample')
    torch.set_num_threads(8)
    model,tok,identity=load_checkpoint(args.checkpoint,'cuda',allow_research=True)
    roots=[9,5,0,7, 9,4,5,0,2,9,5,7, 5,7,4,9, 0,7,9,4,5,0,2,7, 0,7,5,7, 9,5,7,0]
    chords=tuple(Chord(r,'minor' if r in (2,4,9) else 'major') for r in roots)
    sections=(Section('intro',0,4,1),Section('verse',4,8,1),Section('prechorus',12,4,2),
              Section('chorus',16,8,3),Section('chorus',24,4,3),Section('outro',28,4,1))
    plan=SongPlan('ballad','지치지만 아침마다 출근해 일하며 살아 있음을 느끼고 오늘도 최선을 다하겠다는 마음',
                  'tired but purposeful and hopeful','ko',BPM,32,SEED,sections,chords,
                  parts=('piano_rh','piano_lh'),groove='straight',texture='arpeggio',density=1,
                  instruments={'piano_rh':'acoustic_piano','piano_lh':'acoustic_piano'})
    slots,lines=lyric_slots()
    bars,history,placements,reports,previous=[],[],[],[],[]
    for bar,chord in enumerate(chords):
        if bar==31:
            row=dict(length=48,meter=[4,4],notes=[[0,48,48,52],[0,48,55,44],[0,48,72,68]])
            encoded=tok.encode_bar(row)
            report=dict(bar=bar,source='authored final C-major tonic, melody C5')
            placed=[]
        else:
            row,encoded,placed,report=sampled_bar(model,tok,history,chord,bar,slots.get(bar),previous)
        bars.append(row);history.append(encoded);placements+=placed;reports.append(report)
        print(json.dumps(dict(bar=bar+1,notes=len(row['notes']))),flush=True)
    metadata=dict(title=TITLE,key='C major',genre='piano ballad',bpm=BPM,seed=SEED,
        image_sha256=args.image_sha256,image_not_copied=True,
        image_observation='Office work desk with two monitors, notes and overhead lighting. Screen text and personal details not transcribed.',
        user_mood=plan.description,usage_profile='research-noncommercial',
        checkpoint_sha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        model_condition={'mode':'major','style':'romantic'},
        note_source='fresh joint-piano checkpoint inference for melody pitches and velocities',
        authored_controls='original Korean lyrics; 2-bar lyric rhythm; chord progression; LH broken chords; phrase register and contour; final tonic',
        training_scope='existing actual-score piano model; no new training and no claimed learned ballad/lyric/image semantics',
        audio_scope='one acoustic piano playing both melody and accompaniment; no human or synthesized sung vocal',
        form_labels={0:'Intro',4:'Verse',12:'Pre-Chorus',16:'Chorus',24:'Final Hook',28:'Outro'},generation=reports)
    events=tuple(ScoreEvent(b,F(o,12),F(d,12),'piano_lh' if p<60 else 'piano_rh',p,v)
                 for b,row in enumerate(bars) for o,d,p,v in row['notes'])
    composition=Composition(plan,events,metadata)
    plain=ET.fromstring(piano_musicxml(composition,title=TITLE))
    # Set section-specific dynamic labels rather than compatibility exporter defaults.
    dynamics={0:'p',4:'mp',12:'mp',16:'mf',24:'mf',28:'p'}
    for b,m in enumerate(plain.find('part').findall('measure')):
        for node in m.findall('direction/direction-type/dynamics'):
            for child in list(node):node.remove(child)
            ET.SubElement(node,dynamics.get(b,'mp'))
    lyrical=deepcopy(plain)
    add_lyrics(lyrical,placements)
    for name,tree in [('piano',lyrical),('piano-only',plain)]:
        out=args.output/name
        out.mkdir(parents=True,exist_ok=True)
        (out/'score.musicxml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(tree,encoding='unicode'),encoding='utf-8')
        write_midi(composition,out/'score.mid')
        (out/'composition.json').write_text(json.dumps(composition.to_dict(),ensure_ascii=False,indent=2),encoding='utf-8')
        assert sorted(read_piano_xml_events(ET.tostring(tree,encoding='unicode')))==sorted(
            (e.bar,e.onset,e.duration,e.pitch,e.part) for e in events)
    assert ''.join(t.text for t in lyrical.findall('.//lyric/text'))==''.join(line['text'].replace(' ','') for line in lines)
    args.output.mkdir(exist_ok=True)
    for name,data in [('provenance.json',metadata),('lyric-cues.json',lines),('lyric-placements.json',placements)]:
        (args.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    text=TITLE+'\n피아노 발라드 / C장조 / 72 BPM / 4/4박자 / 32마디\n'
    section=None;lrc=[]
    for line in lines:
        if line['section']!=section:
            section=line['section'];text+='\n['+section+']\n'
        text+=line['text']+'\n'
        seconds=line['start_seconds']
        lrc.append('[%02d:%05.2f]%s'%(int(seconds//60),seconds%60,line['text']))
    (args.output/'lyrics.txt').write_text(text,encoding='utf-8')
    (args.output/'lyrics.lrc').write_text('\n'.join(lrc)+'\n',encoding='utf-8')
    result=dict(title=TITLE,bars=32,bpm=BPM,music_seconds=32*240/BPM,piano_notes=len(events),
                lyric_lines=len(lines),lyric_syllables=len(placements),piano_xml_roundtrip=True,
                whole_lyrics_preserved=True,checkpoint_sha256=metadata['checkpoint_sha256'])
    (args.output/'generation-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
