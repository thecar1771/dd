from copy import deepcopy
import pytest
from omr.piano_rich.data import combine_pieces


def piece(i,composer,split,notes):
    return dict(id=i,composer=composer,group=composer.lower(),composer_group=composer.lower(),
                work_key=i,split=split,source='dcml',license='CC-BY-NC-SA-4.0',
                mode='major',style='romantic',instrument='piano',usage_profile='research-noncommercial',
                bars=[dict(length=48,meter=[4,4],notes=notes)])


def test_frozen_composer_holdout_and_original_rows_preserved():
    old=[piece('a','Chopin','validation',[[0,12,60,68],[12,12,64,68]]),
         piece('b','Bach','test',[[0,24,48,52],[12,12,67,76]]),
         piece('c','Mozart','train',[[0,12,55,52],[24,12,72,84]])]
    snapshot=deepcopy(old)
    extra=[piece('d','Chopin','train',[[0,6,60,68],[6,18,65,68]])]
    combined,rejected=combine_pieces(old,extra)
    assert old==snapshot and combined[:3]==old and not rejected
    assert combined[-1]['split']=='validation'


def test_redownload_and_transposition_are_not_new_scores():
    old=[piece('a','Bach','test',[[0,12,60,68],[12,12,64,68]])]
    extra=[piece('b','Other','train',[[0,12,62,68],[12,12,66,68]])]
    combined,rejected=combine_pieces(old,extra)
    assert combined==old and len(rejected)==1
    assert rejected[0]['reason']=='duplicate_content_or_transposition'


def test_same_work_variant_not_inflated_and_conflicting_old_split_rejected():
    a=piece('a','Bach','test',[[0,12,60,68]])
    b=piece('b','Bach','train',[[0,6,63,68],[12,12,72,68]])
    b['work_key']='a'
    assert len(combine_pieces([a],[b])[1])==1
    with pytest.raises(ValueError,match='composer'):
        combine_pieces([a,b],[])
