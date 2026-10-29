"""Remove late-audit ensemble/staff ambiguities from the validated snapshot."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

base=Path(__file__).resolve().parent
feature=Path('C:/Users/theca/orca/workspaces/OMR/omr-genre-bootstrap')
sys.path.insert(0,str(feature/'src'))
from omr.piano_rich.data import read_rows
from omr.piano_rich.train import read_manifest
prior=feature/'artifacts/rich-piano-data-final-20261029'
out=feature/'artifacts/rich-piano-data-final-20261029-v3'
if out.exists() and any(out.iterdir()):raise FileExistsError(out)
candidates={p['id']:p for p in read_rows(base/'input-snapshot-v1/candidates.jsonl')}
rows=read_rows(prior/'pieces.jsonl');kept=[];rejected=[]
assert all(row['id'] not in candidates for row in rows[:1215])
assert all(row['id'] in candidates for row in rows[1215:])
for row in rows:
    reason=None
    if row['id'] in candidates:
        cand=candidates[row['id']]
        staff={v for bar in row['bars'] for v in bar['note_staff']}
        context=' '.join(str(cand.get(k,'')) for k in ('raw_path','title','instrumentation','genre'))
        flags=('orphan_tie_continuations','underfull_voice_measures','merge_with_unequal_voice_time',
               'silent_voice_gaps_without_rest','chords_with_mixed_durations','pitchless_tokens_treated_as_spacers')
        uncertain={flag:max(row.get('conversion',{}).get(flag,0),cand.get('check_report',{}).get(flag,0))
                   for flag in flags}
        if not staff<= {1,2}:reason='withheld: more than two staff identities need separate hand audit'
        elif row['group']=='chopin' and cand.get('opus')==73:reason='withheld: Chopin Op73 two-piano ensemble source'
        elif re.search(r'(?i)(secondo|4[ -]?hands|four[ -]?hands|two[ -]?pianos|2[ -]?pianos|vierh)',context):reason='withheld: possible piano ensemble/part'
        elif any(uncertain.values()):reason='withheld: timing/tie ambiguity '+str({k:v for k,v in uncertain.items() if v})
    if reason:rejected.append(dict(id=row['id'],reason=reason))
    else:kept.append(row)
out.mkdir(parents=True)
manifest=out/'pieces.jsonl'
manifest.write_bytes(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in kept).encode())
read_manifest(manifest)
summary=json.loads((prior/'summary.json').read_text(encoding='utf-8'))
summary.update(late_audit_rejections=len(rejected),files=len(kept),
               accepted_additional_files=len(kept)-1215,works=len({(p['group'],p['work_key']) for p in kept}),
               sources=dict(Counter(p['source'] for p in kept)),splits=dict(Counter(p['split'] for p in kept)),
               composers=len({p['group'] for p in kept}),bars=sum(len(p['bars']) for p in kept),
               notes=sum(len(b['notes']) for p in kept for b in p['bars']),
               split_notes={s:sum(len(b['notes']) for p in kept if p['split']==s for b in p['bars']) for s in ('train','validation','test')},
               manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
               frozen_input_hashes=json.loads((base/'input-snapshot-v1/hashes.json').read_text()),
               strict_timing_audit=True,
               late_audit_policy='exclude third staff identities and possible piano ensemble parts; no source reinterpretation')
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'late-audit-rejections.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2),encoding='utf-8')
for name in ('integration-rejections.json','merge-rejections.json'):(out/name).write_bytes((prior/name).read_bytes())
assert summary['accepted_additional_files']>100
print(json.dumps(summary,ensure_ascii=True),flush=True)
