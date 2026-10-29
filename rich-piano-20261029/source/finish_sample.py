"""Run once, after the successful six-epoch fresh training exit."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
root=Path('/run')
assert (root/'final-exit-code.txt').read_text().strip()=='0'
result=json.loads((root/'final/results.json').read_text())
assert len(result['epochs'])==6 and result['identity']['fresh_initialization']
assert result['identity']['initial_checkpoint'] is None
assert result['identity']['manifest_sha256']=='a6b9f6959d9428650132d77351adc0ebc1673aefd4de4a3cec14b36bf96c73c1'
for epoch in result['epochs']:
    assert epoch['seen_windows']==result['dataset']['train']['windows']
    assert epoch['seen_target_tokens']==result['dataset']['train']['target_tokens']
    assert len(epoch['seen_files'])==1403
subprocess.run([sys.executable,'/work/make_rich_ballad.py','--checkpoint','/run/final/best.pt',
                '--baseline','/run/baseline','--output','/run/sample','--device','cuda'],check=True)
subprocess.run([sys.executable,'/run/make_performance.py','--midi','/run/sample/piano/score.mid',
                '--output','/run/sample/performance.mid'],check=True)
(root/'sample/performance-source.json').write_text(json.dumps(dict(
    path='source/make_piano_performance.py',sha256=hashlib.sha256((root/'make_performance.py').read_bytes()).hexdigest(),
    scope='post-training playback processor; core training source unchanged'),indent=2))
print(json.dumps(dict(sample_generated=True,selected_epoch=result['best_epoch'],
                      checkpoint_sha256=result['checkpoint_hashes']['best.pt'])),flush=True)
