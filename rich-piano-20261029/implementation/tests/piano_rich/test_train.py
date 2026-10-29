import json
import pytest
import torch
from omr.piano_rich.train import train, load_checkpoint, without_context, read_manifest, CHECKPOINT_FORMAT
from omr.piano_rich.tokenizer import RichPianoTokenizer


def test_context_ablation_keeps_identical_targets_and_condition_masks():
    tok=RichPianoTokenizer()
    b=dict(length=48,notes=[[0,12,60,68]])
    windows=tok.windows(dict(mode='major',style='romantic',bars=[b,b,b,b]),max_tokens=40,context_bars=2)
    ablated=without_context(windows,tok)
    assert sum(sum(mask) for ids,mask in ablated)==sum(sum(mask) for ids,mask in windows)
    for ids,mask in ablated:
        assert not any(mask[:9])


def test_audited_humdrum_source_is_research_only(tmp_path):
    row=dict(id='fixture',source='humdrum',composer='Scott Joplin',work_key='fixture',split='train',
             license='CC-BY-NC-SA-4.0',usage_profile='research-noncommercial',instrument='piano',
             mode='major',style='jazz',bars=[dict(length=48,notes=[[0,12,60,68]])])
    manifest=tmp_path/'research.jsonl';manifest.write_text(json.dumps(row),encoding='utf-8')
    assert read_manifest(manifest)[0]['source']=='humdrum'
    with pytest.raises(ValueError,match='commercial'):
        read_manifest(manifest,usage_profile='commercial-compatible')
    row.update(source='nifc',license='CC-BY-4.0',usage_profile='commercial-compatible')
    manifest.write_text(json.dumps(row),encoding='utf-8')
    assert read_manifest(manifest,usage_profile='commercial-compatible')[0]['source']=='nifc'


def test_real_training_coverage_and_safe_own_format(tmp_path):
    rows=[]
    for i,split in enumerate(('train','validation','test')):
        rows.append(dict(id='real-fixture-'+split,source='dcml',composer='Composer'+str(i),
                         group='composer'+str(i),composer_group='composer'+str(i),
                         work_key='work'+str(i),split=split,license='CC-BY-NC-SA-4.0',
                         usage_profile='research-noncommercial',instrument='piano',mode='major',style='romantic',
                         source_sha256='a'*64,bars=[dict(length=48,meter=[4,4],notes=[
                            [0,24,48+i,52],[0,12,60+i,68],[0,12,64+i,76],[12+6*i,12,67+i,84]])]))
    manifest=tmp_path/'pieces.jsonl'
    manifest.write_text(''.join(json.dumps(p)+'\n' for p in rows),encoding='utf-8')
    result=train(manifest,tmp_path/'run',epochs=1,batch_size=1,device='cpu',precision='float32',
                 max_tokens=64,context_bars=1,d_model=16,num_layers=1,nhead=2,dim_feedforward=32,
                 progress_seconds=1,checkpoint_seconds=300)
    assert result['seen_target_tokens']==18
    assert result['epochs'][0]['seen_windows']==1
    with pytest.raises(ValueError,match='research'):
        load_checkpoint(tmp_path/'run/best.pt')
    model,tok,identity=load_checkpoint(tmp_path/'run/best.pt',allow_research=True)
    assert identity['format']==CHECKPOINT_FORMAT=='omr-rich-piano-checkpoint-v1'
    assert 'ROLE_inner' in tok.ids
    assert torch.isfinite(model(torch.tensor([[tok.ids['BOS']]]))).all()
    continued=train(manifest,tmp_path/'run-continued',initial_checkpoint=tmp_path/'run/final.pt',
                 epochs=1,batch_size=1,device='cpu',precision='float32',max_tokens=64,context_bars=1,
                 d_model=16,num_layers=1,nhead=2,dim_feedforward=32,progress_seconds=1,checkpoint_seconds=300)
    assert continued['identity']['fresh_initialization'] is False
    assert continued['identity']['initial_checkpoint']['manifest_sha256']==identity['manifest_sha256']
    rows[0]['split'],rows[1]['split']=rows[1]['split'],rows[0]['split']
    moved=tmp_path/'changed-splits.jsonl'
    moved.write_text(''.join(json.dumps(p)+'\n' for p in rows),encoding='utf-8')
    with pytest.raises(ValueError,match='split'):
        train(moved,tmp_path/'run-rejected',initial_checkpoint=tmp_path/'run/final.pt',
              epochs=1,batch_size=1,device='cpu',precision='float32',max_tokens=64,context_bars=1,
              d_model=16,num_layers=1,nhead=2,dim_feedforward=32,progress_seconds=1,checkpoint_seconds=300)
