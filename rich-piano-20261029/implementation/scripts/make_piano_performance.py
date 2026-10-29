"""Traceable piano-only playback expression; never overwrites score-exact MIDI."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import mido


def transform(source,output,seed=20261029):
    if output.exists():raise FileExistsError(output)
    midi=mido.MidiFile(source);tpq=midi.ticks_per_beat
    rng=random.Random(seed);out=mido.MidiFile(type=midi.type,ticks_per_beat=tpq)
    end=0;note_count=0;changes=[];channels=set();prepared=[];source_counts={};all_notes=[]
    for ti,track in enumerate(midi.tracks):
        tick=0;pending={};notes=[];other=[]
        for message in track:
            tick+=message.time
            if message.type=='note_on' and message.velocity:
                key=(message.channel,message.note)
                assert key not in pending
                pending[key]=(tick,message.velocity)
                channels.add(message.channel)
            elif message.type=='note_off' or message.type=='note_on':
                start,velocity=pending.pop((message.channel,message.note))
                notes.append(dict(track=ti,start=start,end=tick,pitch=message.note,channel=message.channel,velocity=velocity))
            elif message.type!='end_of_track' and not (message.type=='control_change' and message.control==64):
                other.append((tick,0,message.copy(time=0)))
        assert not pending;end=max(end,tick)
        grouped=defaultdict(list)
        for n in notes:grouped[n['start']].append(n)
        for onset,group in sorted(grouped.items()):
            jitter=rng.randint(-2,2)
            for rank,n in enumerate(sorted(group,key=lambda n:n['pitch'])):
                delta=jitter+min(rank,3)*2
                n['played_start']=max(0,n['start']+delta)
                n['played_end']=n['end']+delta
                n['played_velocity']=max(1,min(110,n['velocity']+rng.randint(-2,2)))
        all_notes.extend(notes);note_count+=len(notes);prepared.append(other)
    # Both hand tracks address one physical keyboard. Clamp globally even when
    # a repeated pitch changes MIDI channel, retaining the original RNG order.
    by_pitch=defaultdict(list)
    for n in all_notes:by_pitch[n['pitch']].append(n)
    clamped=0
    for pitch,group in by_pitch.items():
        source_order=sorted(group,key=lambda n:n['start'])
        if any(a['end']>b['start'] for a,b in zip(source_order,source_order[1:])):
            raise ValueError('source physical key overlap on pitch '+str(pitch))
        group.sort(key=lambda n:n['played_start'])
        for i,n in enumerate(group):
            if i+1<len(group):
                stop=min(n['played_end'],group[i+1]['played_start']-1)
                clamped+=stop<n['played_end'];n['played_end']=stop
            if n['played_end']<=n['played_start']:
                raise ValueError('humanization leaves no positive physical key duration on pitch '+str(pitch))
    for n in all_notes:
        key=(n['channel'],n['pitch']);source_counts[key]=source_counts.get(key,0)+1
        other=prepared[n['track']]
        other.append((n['played_start'],2,mido.Message('note_on',channel=n['channel'],note=n['pitch'],velocity=n['played_velocity'])))
        other.append((n['played_end'],1,mido.Message('note_off',channel=n['channel'],note=n['pitch'],velocity=0)))
        changes.append(dict(track=n['track'],channel=n['channel'],pitch=n['pitch'],score_onset=n['start'],played_onset=n['played_start'],
                            score_duration=n['end']-n['start'],played_duration=n['played_end']-n['played_start'],
                            score_velocity=n['velocity'],played_velocity=n['played_velocity']))
    pedal_end=end+max(1,tpq//10)
    # One physical damper pedal controls both MIDI piano channels.
    for channel in sorted(channels):
        for bar in range((end+4*tpq-1)//(4*tpq)):
            start=bar*4*tpq
            if bar:prepared[0].append((start+8,0,mido.Message('control_change',channel=channel,control=64,value=0)))
            prepared[0].append((start+(0 if bar==0 else 20),0,mido.Message('control_change',channel=channel,control=64,value=100)))
        prepared[0].append((pedal_end,0,mido.Message('control_change',channel=channel,control=64,value=0)))
    for rows in prepared:
        track=mido.MidiTrack();prior=0
        for tick,priority,message in sorted(rows,key=lambda row:(row[0],row[1])):
            assert tick>=prior
            track.append(message.copy(time=tick-prior));prior=tick
        track.append(mido.MetaMessage('end_of_track',time=max(0,pedal_end+4-prior)));out.tracks.append(track)
    output.parent.mkdir(parents=True,exist_ok=True);out.save(output)
    # Separate reload verifies every physical note-off and final pedal release.
    played=mido.MidiFile(output);counts={};active={};physical={};pedal={};total=0
    for message in mido.merge_tracks(played.tracks):
        if message.type=='note_on' and message.velocity:
            key=(message.channel,message.note)
            if message.note in physical:
                raise ValueError('performance physical key overlap on pitch '+str(message.note))
            assert key not in active;active[key]=1;physical[message.note]=key
            counts[key]=counts.get(key,0)+1;total+=1
        elif message.type=='note_off' or message.type=='note_on':
            key=(message.channel,message.note);active.pop(key)
            if physical.pop(message.note)!=key:
                raise ValueError('performance physical key release differs from MIDI channel')
        elif message.type=='control_change' and message.control==64:pedal[message.channel]=message.value
    assert not active and not physical and total==note_count and counts==source_counts and all(v==0 for v in pedal.values())
    report=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),performance_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                notes=note_count,seed=seed,source_midi_unchanged=True,pitch_inventory_unchanged=True,
                no_hanging_notes=True,no_physical_key_overlap=True,global_duration_clamps=clamped,
                final_pedal_released=True,changes=changes,
                scope='separate expressive playback: tiny chord rolls/timing, authored balance, damper pedal; score-exact MIDI retained')
    output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='changes'}),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--midi',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();transform(args.midi,args.output)
