"""Fail-closed integration of independently audited real score rows."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

feature=Path('C:/Users/theca/orca/workspaces/OMR/omr-genre-bootstrap')
main=Path('C:/Users/theca/orca/projects/OMR')
sys.path.insert(0,str(feature/'src'))
from omr.piano_rich.data import read_rows,combine_pieces
from omr.piano_rich.tokenizer import RichPianoTokenizer
from omr.piano_rich.train import read_manifest

corpus=feature/'artifacts/rich-piano-corpus-20261029'
out=feature/'artifacts/rich-piano-data-final-20261029'
if out.exists() and any(out.iterdir()):raise FileExistsError(out)
old=read_rows(main/'artifacts/piano-only-20261028-final/data/pieces.jsonl.gz')
assert len(old)==1215
candidates={p['id']:p for p in read_rows(corpus/'candidates.jsonl')}
new=[];rejected=[];tok=RichPianoTokenizer();adapted=0
paths=sorted((corpus/'rows').glob('pieces-*.jsonl.gz'))
assert paths,'Claude canonical output missing'
for path in paths:
    for row in read_rows(path):
        try:
            candidate=candidates[row['id']]
            assert candidate['accepted'] is True,'not accepted by curator'
            assert row['composer'].strip(),'empty composer'
            group=row.get('piano_music_group') or candidate.get('piano_music_group')
            assert group and group!='unknown','unresolved composer identity'
            report=row.get('conversion',{})
            for flag in ('orphan_tie_continuations','underfull_voice_measures','unequal_time_spine_merges'):
                assert not report.get(flag,0),(flag,report.get(flag))
                assert not candidate.get('check_report',{}).get(flag,0),(flag,'candidate')
            raw=(corpus/candidate['raw_path']).read_bytes()
            assert hashlib.sha256(raw).hexdigest()==row['source_sha256']==candidate['sha256'],'source changed'
            row=dict(row,composer_group=group,group=group,source_url=row.get('source_url') or row['url'])
            for bar in row['bars']:
                ties=bar['note_tie_from_previous_bar']
                assert all(type(v) is bool or type(v) is int and v in (0,1) for v in ties),'invalid attack evidence'
                adapted+=sum(type(v) is int for v in ties)
                bar['note_tie_from_previous_bar']=[bool(v) for v in ties]
                tokens=tok.encode_bar(bar)
                assert len(tokens)+len(tok.prefix(row['mode'],row['style']))<=2048,'whole bar exceeds context'
            new.append(row)
        except Exception as error:
            rejected.append(dict(id=row['id'],reason=type(error).__name__+': '+str(error)))
rows,duplicates=combine_pieces(old,new)
out.mkdir(parents=True)
manifest=out/'pieces.jsonl'
manifest.write_bytes(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows).encode())
checked=read_manifest(manifest)
assert len(checked)==len(rows)
for row in rows:
    for bar in row['bars']:tok.encode_bar(bar)
summary=dict(original_files=len(old),additional_emitted_files=sum(len(read_rows(p)) for p in paths),
             validated_additional_files=len(new),integration_rejections=len(rejected),
             merge_rejections=len(duplicates),accepted_additional_files=len(rows)-len(old),
             files=len(rows),works=len({(p['group'],p['work_key']) for p in rows}),
             sources=dict(Counter(p['source'] for p in rows)),splits=dict(Counter(p['split'] for p in rows)),
             composers=len({p['group'] for p in rows}),
             bars=sum(len(p['bars']) for p in rows),notes=sum(len(b['notes']) for p in rows for b in p['bars']),
             split_notes={s:sum(len(b['notes']) for p in rows if p['split']==s for b in p['bars']) for s in ('train','validation','test')},
             bool_tie_adaptations=adapted,manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
             old_composer_splits_frozen=True,synthetic_training_pieces=0,usage_profile='research-noncommercial',
             phase1_quarantined=True,final_initialization='fresh weights; no phase1 checkpoint')
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'integration-rejections.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'merge-rejections.json').write_text(json.dumps(duplicates,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary),flush=True)
