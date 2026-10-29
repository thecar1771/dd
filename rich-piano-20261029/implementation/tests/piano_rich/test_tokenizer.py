from copy import deepcopy
import pytest
from omr.piano_rich.tokenizer import RichPianoTokenizer, describe_bar


def bar():
    return dict(length=48,meter=[4,4],notes=[
        [0,24,48,52],[0,12,60,60],[0,12,64,68],[0,12,72,84],
        [12,12,55,52],[12,12,67,76],[24,24,48,52],[24,24,65,68],[24,24,69,84]])


def test_polyphonic_roles_and_exact_roundtrip():
    t=RichPianoTokenizer()
    b=bar();encoded=t.encode_bar(b)
    result=t.decode_bar(encoded)
    assert result['notes']==b['notes']
    names=[t.tokens[i] for i in encoded]
    assert 'ROLE_inner' in names and 'ROLE_melody' in names and 'ROLE_bass' in names
    assert t.encode_bar(result)==encoded
    assert describe_bar(b)['polyphony']=='full'


def test_conditions_are_visible_but_never_loss_targets():
    t=RichPianoTokenizer()
    p=dict(id='a',mode='major',style='romantic',bars=[bar() for _ in range(9)])
    windows=t.windows(p,max_tokens=120,context_bars=2)
    seen_bars=0
    for ids,mask in windows:
        assert not any(mask[:3])
        for i,k in enumerate(ids):
            if t.tokens[k]=='BAR':
                assert not any(mask[i:i+6])
            if t.tokens[k]=='END_BAR' and mask[i]:seen_bars+=1
    assert seen_bars==9
    assert sum(t.tokens[k]=='EOS' and m for ids,mask in windows for k,m in zip(ids,mask))==1


def test_dense_bar_is_not_truncated_and_same_key_overlap_rejected():
    t=RichPianoTokenizer()
    with pytest.raises(ValueError,match='too dense'):
        t.windows(dict(mode='major',style='romantic',bars=[bar()]),max_tokens=20)
    b=bar();b['notes'].append([1,4,48,60])
    with pytest.raises(ValueError,match='overlap'):t.encode_bar(b)


def test_empty_and_short_bars_are_preserved():
    t=RichPianoTokenizer()
    for b in [dict(length=12,meter=[1,4],notes=[]),dict(length=6,meter=[1,8],notes=[[0,6,64,68]])]:
        result=t.decode_bar(t.encode_bar(b))
        assert result['length']==b['length'] and result['notes']==b['notes']


def test_score_velocities_are_context_but_not_prediction_targets():
    t=RichPianoTokenizer()
    windows=t.windows(dict(mode='major',style='romantic',bars=[bar()]))
    assert all(not mask[i] for ids,mask in windows for i,k in enumerate(ids)
               if t.tokens[k].startswith('VELOCITY_'))


def test_explicit_planned_controls_are_traceable_not_silently_recomputed():
    t=RichPianoTokenizer();b=bar()
    b['controls']=dict(density='dense',polyphony='full',texture='mixed',harmony='major')
    assert t.decode_bar(t.encode_bar(b))['controls']==b['controls']
    b['controls']['texture']='not-a-label'
    with pytest.raises(ValueError):t.encode_bar(b)


def test_available_true_staff_handles_crossing_hands_without_pitch_cutoff():
    t=RichPianoTokenizer()
    b=dict(length=48,notes=[[0,12,55,68],[0,12,64,52]],note_staff=[1,2])
    assert t.decode_bar(t.encode_bar(b))['roles']==['melody','bass']


def test_cross_bar_continuation_is_explicit_and_unknown_legacy_flags_not_targets():
    t=RichPianoTokenizer()
    b=dict(length=48,notes=[[0,24,48,52],[0,12,64,68]],note_tie_from_previous_bar=[True,False])
    encoded=t.encode_bar(b)
    assert t.decode_bar(encoded)['attacks']==['held','new']
    ids,mask=t.windows(dict(mode='major',style='romantic',bars=[b]))[0]
    assert any(t.tokens[k]=='ATTACK_held' and m for k,m in zip(ids,mask))
    old=dict(length=48,notes=[[0,12,60,68]])
    ids,mask=t.windows(dict(mode='major',style='romantic',bars=[old]))[0]
    assert any(t.tokens[k]=='ATTACK_unknown' and not m for k,m in zip(ids,mask))
