"""Merge additional actual scores while freezing the previous composer holdouts."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
from omr.piano_music.data import composer_key


def _composer(piece):
    return re.sub('[^a-z0-9]','',str(piece.get('composer_group') or piece.get('group') or composer_key(piece['composer'])).lower())


def _fingerprints(piece):
    bars=[(b['length'],sorted([list(n[:3]) for n in b['notes']],key=lambda n:(n[0],n[2]))) for b in piece['bars']]
    base=next((n[2] for length,notes in bars for n in notes),0)
    relative=[(length,[[o,d,p-base] for o,d,p in notes]) for length,notes in bars]
    return tuple(hashlib.sha256(json.dumps(x,separators=(',',':')).encode()).hexdigest() for x in (bars,relative))


def combine_pieces(existing,additional,seed=20261029):
    assignments={};works=set();ids=set();fingerprints=set()
    for piece in existing:
        composer=_composer(piece)
        if composer in assignments and assignments[composer]!=piece['split']:
            raise ValueError('conflicting existing composer split: '+composer)
        assignments[composer]=piece['split']
        works.add((composer,piece['work_key']))
        ids.add(piece['id']);fingerprints.update(_fingerprints(piece))
    combined=list(existing);rejected=[]
    for piece in sorted(additional,key=lambda p:p['id']):
        composer=_composer(piece)
        fp=_fingerprints(piece)
        reason=('duplicate_content_or_transposition' if any(f in fingerprints for f in fp)
                else 'existing_work_variant' if (composer,piece['work_key']) in works
                else 'duplicate_id' if piece['id'] in ids else None)
        if reason:
            rejected.append(dict(id=piece['id'],reason=reason));continue
        if composer not in assignments:
            bucket=int(hashlib.sha256((str(seed)+':'+composer).encode()).hexdigest()[:8],16)%100
            assignments[composer]='train' if bucket<80 else 'validation' if bucket<90 else 'test'
        row=dict(piece,split=assignments[composer],group=composer,composer_group=composer,newly_collected=True)
        combined.append(row);ids.add(row['id']);fingerprints.update(fp)
        # New distinct movements in an entirely new work can be retained together.
        # Existing-base works were frozen before the loop and remain excluded.
    return combined,rejected


def read_rows(path):
    path=Path(path)
    data=gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes()
    return [json.loads(line) for line in data.decode('utf-8-sig').splitlines() if line.strip()]


def main():
    import argparse
    from .train import read_manifest
    ap=argparse.ArgumentParser()
    ap.add_argument('--base',type=Path,required=True)
    ap.add_argument('--additional',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists() and any(args.output.iterdir()):raise FileExistsError(args.output)
    old,new=read_rows(args.base),read_rows(args.additional)
    rows,rejected=combine_pieces(old,new)
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=args.output/'pieces.jsonl'
    manifest.write_bytes(''.join(json.dumps(p,ensure_ascii=False,separators=(',',':'))+'\n' for p in rows).encode('utf-8'))
    checked=read_manifest(manifest)
    assert len(checked)==len(rows)
    summary=dict(original_files=len(old),additional_candidates=len(new),accepted_additional_files=len(rows)-len(old),
                 rejected_additional_files=len(rejected),files=len(rows),
                 works=len({(_composer(p),p['work_key']) for p in rows}),
                 sources=dict(Counter(p['source'] for p in rows)),splits=dict(Counter(p['split'] for p in rows)),
                 bars=sum(len(p['bars']) for p in rows),notes=sum(len(b['notes']) for p in rows for b in p['bars']),
                 previous_composer_splits_frozen=True,manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                 synthetic_training_pieces=0,usage_profile='research-noncommercial')
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'merge-rejections.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
