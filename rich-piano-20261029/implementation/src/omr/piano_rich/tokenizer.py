"""Observed texture controls and weak outer-voice labels for exact piano events.

Controls are derived from real target bars, supplied as inputs and not scored.
Voice labels describe note geometry; they are NOT annotated hands/voice truth.
"""
from collections import Counter
from omr.piano_music.tokenizer import PianoTokenizer as BaseTokenizer

FORMAT='omr-rich-piano-tokens-v1'
CONTROL_VALUES={
    'density':('sparse','flowing','dense'),
    'polyphony':('mono','layered','full'),
    'texture':('single','broken','chordal','mixed'),
    'harmony':('major','minor','other','unknown'),
}
ROLES=('bass','inner','melody')
ATTACKS=('new','held','unknown')


def describe_bar(bar):
    notes=bar['notes'];length=bar['length']
    density=len(notes)*48/length
    positions={n[0] for n in notes}
    peak=max((sum(o<=position<o+d for o,d,p,v in notes) for position in positions),default=0)
    counts=Counter(n[0] for n in notes)
    chord_share=sum(v for v in counts.values() if v>=2)/max(1,len(notes))
    texture=('single' if len(notes)<=1 else 'broken' if peak<=2 and chord_share<.65
             else 'chordal' if chord_share>=.65 else 'mixed')
    histogram=Counter()
    for o,d,p,v in notes:histogram[p%12]+=d
    harmony='unknown'
    if histogram:
        candidates=[]
        for root in range(12):
            for quality,third in [('major',4),('minor',3)]:
                covered=sum(histogram[(root+i)%12] for i in (0,third,7))
                candidates.append((covered,quality,root))
        covered,quality,_=max(candidates)
        harmony=quality if covered/sum(histogram.values())>=.7 else 'other'
    return dict(density='sparse' if density<=6 else 'flowing' if density<=14 else 'dense',
                polyphony='mono' if peak<=1 else 'layered' if peak==2 else 'full',
                texture=texture,harmony=harmony)


def outer_roles(notes,staffs=None):
    at={}
    for o,d,p,v in notes:at.setdefault(o,[]).append(p)
    if staffs is None:staffs=[None]*len(notes)
    right={};left={}
    for (o,d,p,v),staff in zip(notes,staffs):
        if staff==1:right.setdefault(o,[]).append(p)
        if staff==2:left.setdefault(o,[]).append(p)
    roles=[]
    for (o,d,p,v),staff in zip(notes,staffs):
        if staff==1:role='melody' if p==max(right[o]) else 'inner'
        elif staff==2:role='bass' if p==min(left[o]) else 'inner'
        else:role='bass' if p==min(at[o]) and p<60 else 'melody' if p==max(at[o]) else 'inner'
        roles.append(role)
    return roles


class RichPianoTokenizer(BaseTokenizer):
    format=FORMAT
    header_size=6

    def __init__(self):
        super().__init__()
        for name,values in CONTROL_VALUES.items():
            self.tokens.extend(name.upper()+'_'+value for value in values)
        self.tokens.extend('ROLE_'+role for role in ROLES)
        self.tokens.extend('ATTACK_'+attack for attack in ATTACKS)
        self.ids={name:i for i,name in enumerate(self.tokens)}

    def encode_bar(self,bar):
        base=super().encode_bar(bar)
        notes=[]
        for i in range(2,len(base)-1,4):
            names=[self.tokens[t] for t in base[i:i+4]]
            values=[int(name.split('_')[-1]) for name in names]
            values[3]=self.decode_velocity(values[3]);notes.append(values)
        controls=bar.get('controls',describe_bar(dict(length=bar['length'],notes=notes)))
        if set(controls)!=set(CONTROL_VALUES):raise ValueError('all four controls required')
        for key,values in CONTROL_VALUES.items():
            if controls[key] not in values:raise ValueError('unsupported control '+key)
        staffs=None
        if 'note_staff' in bar:
            if len(bar['note_staff'])!=len(bar['notes']):raise ValueError('staff annotations must align to notes')
            lookup={(n[0],n[1],n[2]):s for n,s in zip(bar['notes'],bar['note_staff'])}
            staffs=[lookup[(n[0],n[1],n[2])] for n in notes]
        roles=bar.get('roles',outer_roles(notes,staffs))
        if len(roles)!=len(notes) or any(role not in ROLES for role in roles):
            raise ValueError('one valid weak voice role per note required')
        attacks=bar.get('attacks')
        if attacks is None:
            flags=bar.get('note_tie_from_previous_bar')
            if flags is None:attacks=['unknown']*len(notes)
            else:
                if len(flags)!=len(bar['notes']) or any(f is not None and not isinstance(f,bool) for f in flags):
                    raise ValueError('continuation annotations must align to notes')
                lookup={(n[0],n[1],n[2]):f for n,f in zip(bar['notes'],flags)}
                attacks=[('unknown' if lookup[(n[0],n[1],n[2])] is None else
                          'held' if lookup[(n[0],n[1],n[2])] else 'new') for n in notes]
        if len(attacks)!=len(notes) or any(a not in ATTACKS for a in attacks):raise ValueError('invalid attacks')
        ids=base[:2]+[self.ids[key.upper()+'_'+controls[key]] for key in CONTROL_VALUES]
        for i,role in enumerate(roles):
            pos,dur,pitch,vel=base[2+4*i:6+4*i]
            ids.extend((pos,dur,self.ids['ROLE_'+role],self.ids['ATTACK_'+attacks[i]],pitch,vel))
        return ids+[self.ids['END_BAR']]

    def decode_bar(self,ids):
        if not isinstance(ids,(list,tuple)) or len(ids)<7:
            raise ValueError('malformed rich bar')
        if any(isinstance(i,bool) or not isinstance(i,int) or not 0<=i<len(self.tokens) for i in ids):
            raise ValueError('invalid rich token id')
        names=[self.tokens[i] for i in ids]
        if names[0]!='BAR' or not names[1].startswith('LEN_') or names[-1]!='END_BAR' or (len(ids)-7)%6:
            raise ValueError('malformed rich bar header or note stages')
        controls={}
        for i,key in enumerate(CONTROL_VALUES,2):
            prefix=key.upper()+'_'
            if not names[i].startswith(prefix):raise ValueError('wrong control order')
            controls[key]=names[i][len(prefix):]
            if controls[key] not in CONTROL_VALUES[key]:raise ValueError('unsupported control')
        notes=[];roles=[];attacks=[]
        for i in range(6,len(ids)-1,6):
            values=[]
            for key,name in zip(('POS','DUR','ROLE','ATTACK','PITCH','VELOCITY'),names[i:i+6]):
                if not name.startswith(key+'_'):raise ValueError('wrong note stage')
                if key=='ROLE':roles.append(name[5:])
                elif key=='ATTACK':attacks.append(name[7:])
                else:values.append(int(name.split('_')[-1]))
            values[3]=self.decode_velocity(values[3]);notes.append(values)
        result=dict(length=int(names[1][4:]),notes=notes,controls=controls,roles=roles,attacks=attacks)
        if self.encode_bar(result)!=list(ids):raise ValueError('noncanonical rich bar')
        return result

    def windows(self,piece,max_tokens=2048,context_bars=4):
        result=super().windows(piece,max_tokens,context_bars)
        for ids,mask in result:
            for i,token in enumerate(ids):
                if token==self.ids['BAR']:
                    mask[i:i+self.header_size]=[False]*self.header_size
                elif self.tokens[token].startswith('VELOCITY_') or self.tokens[token]=='ATTACK_unknown':
                    # Score MIDI velocities are often constants/engraving defaults,
                    # not recorded performer expression. Keep as context only.
                    mask[i]=False
        return result


# Trainer compatibility alias; checkpoint FORMAT remains separate from old weights.
PianoTokenizer=RichPianoTokenizer
