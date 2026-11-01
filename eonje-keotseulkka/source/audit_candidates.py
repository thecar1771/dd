"""Run the existing song_coherence audit on every lead candidate.

Selection rule fixed before looking at results: fewest rule issues, ties -> lowest seed.
No listening or semantic score is used.
  PYTHONPATH=<omr-genre-bootstrap>/src python audit_candidates.py
"""
import json
from pathlib import Path
from omr.genres.contracts import Composition
from omr.song_coherence.integration import audit_bundle

HERE=Path(__file__).resolve().parent
rows=[]
for folder in sorted((HERE/'candidates').iterdir()):
    comp=Composition.from_dict(json.loads((folder/'piano/composition.json').read_text(encoding='utf-8')))
    report=audit_bundle(comp,folder)
    issues=[dict(code=i['code'],phrase=i['phrase_id'],details=i.get('details')) for i in report['issues']]
    lead=[e.pitch for e in comp.events if e.part=='piano_rh']
    rows.append(dict(candidate=folder.name,issues=len(issues),issue_list=issues,
                     lead_range=[min(lead),max(lead)],repeated_pitch_ratio=round(sum(a==b for a,b in zip(lead,lead[1:]))/(len(lead)-1),3)))
rows.sort(key=lambda r:(r['issues'],r['candidate']))
result=dict(rule='fewest song_coherence rule issues, ties -> lowest seed; no listening/semantic score',
            selected=rows[0]['candidate'],candidates=rows)
(HERE/'candidate-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=1))
