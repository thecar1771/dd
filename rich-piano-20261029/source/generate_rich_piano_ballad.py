"""Piano-only re-arrangement: preserve the original lead, infer new inner voicings."""
import argparse
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import torch
from omr.genres.contracts import Composition,ScoreEvent
from omr.genres.export import write_midi
from omr.piano_music.export import piano_musicxml,read_piano_xml_events
from omr.piano_rich.tokenizer import describe_bar
from omr.piano_rich.train import load_checkpoint

TITLE='오늘도, 나의 자리 · 피아노 확장편곡'


def intersects(a,b):return a[0]<b[0]+b[1] and b[0]<a[0]+a[1]


@torch.inference_mode()
def arrange_bar(model,tok,history,chord,bar,lead,seed,previous_inner):
    device=next(model.parameters()).device
    rng=torch.Generator(device=device).manual_seed(seed+104729*bar)
    chorus=16<=bar<28;quiet=bar<4 or bar>=28
    controls=dict(density='sparse' if quiet else 'dense' if chorus else 'flowing',
                  polyphony='full',texture='mixed',harmony=chord.quality)
    header=tok.encode_bar(dict(length=48,notes=[],controls=controls))[:-1]
    current=list(header);rows=[];sampled=0;skipped=0
    prefix=tok.prefix('major','romantic')
    pcs={(chord.root+i)%12 for i in (0,3 if chord.quality=='minor' else 4,7)}
    extensions=pcs|{(chord.root+(10 if chord.root==7 or chord.quality=='minor' else 11))%12}
    if chord.root in (0,2,5,9):extensions.add((chord.root+2)%12)
    # Explicit section textures; note choice among legal options uses new logits.
    lh=[(0,24,'root'),(24,24,'root')] if quiet else (
        [(0,18,'root'),(6,6,'arp'),(12,6,'arp'),(18,6,'arp'),(24,18,'root'),(30,6,'arp'),(36,6,'arp'),(42,6,'arp')] if chorus else
        [(0,18,'root'),(12,6,'arp'),(18,6,'arp'),(24,12,'root'),(36,6,'arp'),(42,6,'arp')] if bar%2==0 else
        [(0,24,'root'),(12,6,'arp'),(18,6,'arp'),(24,18,'root'),(36,6,'arp'),(42,6,'arp')])
    slots=[dict(o=o,d=d,kind=kind,hand='piano_lh',role='bass') for o,d,kind in lh]
    for o in ((0,) if quiet else (0,24)):
        for member in range(2 if chorus else 1):
            slots.append(dict(o=o,d=24,kind='inner',hand='piano_rh',role='inner',member=member))
    for e in lead:
        slots.append(dict(o=int(e.onset*12),d=int(e.duration*12),kind='melody',hand='piano_rh',
                          role='melody',pitch=e.pitch,velocity=e.velocity))
    slots.sort(key=lambda s:(s['o'],{'root':0,'arp':0,'inner':1,'melody':2}[s['kind']],s.get('member',0)))

    def choose(pitches):
        nonlocal sampled
        if len(pitches)==1:return pitches[0]
        kept=list(history)
        while len(prefix)+sum(map(len,kept))+len(current)>model.config.max_sequence_length:
            kept.pop(0)
        ids=prefix+[t for b in kept for t in b]+current
        logits=model(torch.tensor([ids],device=device))[0,-1].float()
        choices=torch.tensor([tok.ids['PITCH_'+str(p)] for p in pitches],device=device)
        probabilities=torch.softmax(logits[choices]/.63,dim=-1)
        assert torch.isfinite(probabilities).all()
        sampled+=1
        return pitches[torch.multinomial(probabilities,1,generator=rng).item()]

    for slot in slots:
        o,d=slot['o'],slot['d'];kind=slot['kind'];hand=slot['hand']
        if kind=='melody':pitches=[slot['pitch']]
        elif kind=='root':
            target_pc=chord.root if o==0 or bar%4!=3 else (chord.root+7)%12
            pitches=[p for p in range(36,55) if p%12==target_pc]
        elif kind=='arp':
            pitches=[p for p in range(43,61) if p%12 in pcs]
        else:
            overlapping=[e.pitch for e in lead if intersects((o,d),(int(e.onset*12),int(e.duration*12)))]
            low=max(50,(max(overlapping)-12) if overlapping else 55)
            high=min(72,(min(overlapping)-3) if overlapping else 65)
            pitches=[p for p in range(low,high+1) if p%12 in extensions]
            if previous_inner and len(pitches)>2:
                close=[p for p in pitches if abs(p-previous_inner[-1])<=7]
                if close:pitches=close
        if kind!='melody':
            safe=[]
            for p in pitches:
                if any(p==r['p'] and intersects((o,d),(r['o'],r['d'])) for r in rows):continue
                if any(p==e.pitch and intersects((o,d),(int(e.onset*12),int(e.duration*12))) for e in lead):continue
                same_onset=[r['p'] for r in rows if r['o']==o]
                if same_onset and p<=max(same_onset):continue
                active=[r['p'] for r in rows if r['hand']==hand and intersects((o,d),(r['o'],r['d']))]
                # A written held bass occupies a finger even when a pedal is
                # available. Bound both hands, not only simultaneous attacks.
                if active and max(active+[p])-min(active+[p])>12:continue
                if len(active)>=5:continue
                if hand=='piano_rh':
                    if any(abs(p-q) in (1,2) for q in active):continue
                    if any(abs(p-e.pitch) in (1,2) for e in lead if intersects((o,d),(int(e.onset*12),int(e.duration*12)))):continue
                safe.append(p)
            pitches=safe
            if not pitches:skipped+=1;continue
        current += [tok.ids['POS_'+str(o)],tok.ids['DUR_'+str(d)],tok.ids['ROLE_'+slot['role']],tok.ids['ATTACK_new']]
        pitch=choose(pitches);current.append(tok.ids['PITCH_'+str(pitch)])
        # Score-source velocities are not performer supervision. These are authored balance controls.
        velocity=(min(100,slot['velocity']+4) if chorus else slot['velocity']) if kind=='melody' else (
            (56 if chorus else 48 if quiet else 52) if kind=='root' else 48 if kind=='arp' else 56 if chorus else 44)
        current.append(tok.ids['VELOCITY_'+str(tok.encode_velocity(velocity))])
        rows.append(dict(o=o,d=d,p=pitch,v=velocity,hand=hand,role=slot['role']))
        if kind=='inner':previous_inner.append(pitch)
    rows.sort(key=lambda r:(r['o'],r['p']))
    canonical=dict(length=48,meter=[4,4],notes=[[r['o'],r['d'],r['p'],r['v']] for r in rows],
                   roles=[r['role'] for r in rows],note_staff=[1 if r['hand']=='piano_rh' else 2 for r in rows],
                   note_tie_from_previous_bar=[False]*len(rows),controls=controls)
    encoded=tok.encode_bar(canonical)
    return rows,encoded,dict(bar=bar,model_pitch_choices=sampled,skipped_unplayable_slots=skipped,
                             requested_controls=controls,actual_features=describe_bar(canonical))


def add_lyrics(root,placements):
    lookup={(p['bar'],p['onset'],p['pitch']):p for p in placements};assigned=set()
    steps=dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11);divisions=1
    for b,m in enumerate(root.find('part').findall('measure')):
        divisions=int(m.findtext('attributes/divisions') or divisions);cursor=F(0);chord_start=F(0)
        for node in m:
            if node.tag in ('backup','forward'):
                cursor+=(-1 if node.tag=='backup' else 1)*F(int(node.findtext('duration')),divisions)
            elif node.tag=='note':
                duration=F(int(node.findtext('duration')),divisions);chord=node.find('chord') is not None
                onset=chord_start if chord else cursor
                if not chord:chord_start=cursor;cursor+=duration
                p=node.find('pitch')
                if p is None or node.findtext('staff')!='1':continue
                midi=(int(p.findtext('octave'))+1)*12+steps[p.findtext('step')]+int(p.findtext('alter') or 0)
                key=(b,int(onset*12),midi)
                if key in lookup and key not in assigned:
                    lyric=ET.SubElement(node,'lyric',number='1')
                    ET.SubElement(lyric,'syllabic').text='single';ET.SubElement(lyric,'text').text=lookup[key]['lyric']
                    assigned.add(key)
    assert assigned==set(lookup)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--checkpoint',type=Path,required=True)
    ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--device',default='cuda');ap.add_argument('--seed',type=int,default=2026102911)
    args=ap.parse_args()
    if args.output.exists() and any(args.output.iterdir()):raise FileExistsError(args.output)
    torch.set_num_threads(8)
    model,tok,identity=load_checkpoint(args.checkpoint,args.device,allow_research=True)
    baseline=Composition.from_dict(json.loads((args.baseline/'piano/composition.json').read_text(encoding='utf-8')))
    history=[];events=[];reports=[];previous=[]
    for bar,chord in enumerate(baseline.plan.chords):
        lead=[e for e in baseline.events if e.bar==bar and e.part=='piano_rh']
        rows,encoded,report=arrange_bar(model,tok,history,chord,bar,lead,args.seed,previous)
        history.append(encoded);reports.append(report)
        for r in rows:events.append(ScoreEvent(bar,F(r['o'],12),F(r['d'],12),r['hand'],r['p'],r['v']))
        print(json.dumps(dict(bar=bar+1,notes=len(rows),learned_choices=report['model_pitch_choices'])),flush=True)
    metadata=dict(baseline.metadata,title=TITLE,seed=args.seed,checkpoint_sha256=identity['checkpoint_sha256'],
        model_format=identity['format'],note_source='original lead retained; new learned inner voicings and LH note choices',
        authored_controls='section accompaniment rhythms, chord extensions, voice ranges, melody prominence and pedal/performance controls',
        training_scope='new texture-conditioned actual-score piano model; score velocities excluded as expression targets',
        generation=reports,audio_scope='piano only; score-exact and separately labelled expressive performance MIDI')
    plan=replace(baseline.plan,seed=args.seed)
    composition=Composition(plan,tuple(events),metadata)
    plain=ET.fromstring(piano_musicxml(composition,title=TITLE))
    first=plain.find('part/measure');direction=ET.Element('direction',placement='above')
    ET.SubElement(ET.SubElement(direction,'direction-type'),'words').text='Cantabile; melody above inner voices. Con pedale, change with harmony.'
    first.insert(1,direction)
    for bar,measure in enumerate(plain.find('part').findall('measure')):
        for dynamic in measure.findall('direction/direction-type/dynamics'):
            for child in list(dynamic):dynamic.remove(child)
            ET.SubElement(dynamic,'p' if bar in (0,28) else 'mf' if bar in (16,24) else 'mp')
    lyrical=deepcopy(plain)
    placements=json.loads((args.baseline/'lyric-placements.json').read_text(encoding='utf-8'))
    add_lyrics(lyrical,placements)
    for folder,tree in [('piano',lyrical),('piano-only',plain)]:
        out=args.output/folder;out.mkdir(parents=True,exist_ok=True)
        xml='<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(tree,encoding='unicode')
        (out/'score.musicxml').write_text(xml,encoding='utf-8');write_midi(composition,out/'score.mid')
        (out/'composition.json').write_text(json.dumps(composition.to_dict(),ensure_ascii=False,indent=2),encoding='utf-8')
        assert sorted(read_piano_xml_events(xml))==sorted((e.bar,e.onset,e.duration,e.pitch,e.part) for e in events)
    for name in ('lyrics.txt','lyrics.lrc','lyric-cues.json','lyric-placements.json'):
        (args.output/name).write_bytes((args.baseline/name).read_bytes())
    assert ''.join(n.text for n in lyrical.findall('.//lyric/text'))==''.join(p['lyric'] for p in placements)
    (args.output/'provenance.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(bars=32,notes=len(events),learned_choices=sum(r['model_pitch_choices'] for r in reports),
                         original_lead_preserved=True,checkpoint_sha256=identity['checkpoint_sha256'])),flush=True)

if __name__=='__main__':main()
