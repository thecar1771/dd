"""Editorial lyric review bound to phrase digests (same contract as revise_workday_phrases.py).

  PYTHONPATH=<omr-genre-bootstrap>/src python review_lyrics.py
Copies the selected candidate to reviewed-baseline/, writes editorial-review.json and
lyric-review-log.json, and requires the strict audit to accept. Agent review, not a human label.
"""
import json, shutil
from pathlib import Path
from omr.genres.contracts import Composition
from omr.song_coherence.integration import audit_bundle

HERE=Path(__file__).resolve().parent
REASONS=[
 '사용자 문장 "콩쿠르 대회에 와서"를 그대로 쓴 첫 장면이다.',
 '사용자 문장 "사진을 찍었습니다"와 사진 속 세 사람이 나란히 선 모습을 잇는다.',
 '사진 다음 장면으로 무대 위 딸을 지켜보는 부모의 시선이다.',
 '앞 줄의 지켜봄을 응원하는 행동으로 완결한다.',
 '결과 발표 순간으로 넘어가며 다음 줄을 기다리게 한다.',
 '사용자 문장 "특상도 받았습니다"를 담고, "소식에"로 후렴의 감정으로 이어진다.',
 '사용자 단어 "대견하고 기특합니다"를 딸에게 직접 하는 말로 옮겼다.',
 '사용자 문장 "언제 이렇게 컸는지"를 딸에게 묻는 말로 옮겼다.',
 '"컸니"를 받아 어렸던 시절을 떠올리며 다음 줄로 이어진다.',
 '작던 아이가 무대에 섰다는 대비로 "신기합니다"의 마음을 완결한다.',
 '하루 전체를 가족이 함께 웃은 날로 모은다.',
 '사용자 문장 "가족 덕분에 행복한 하루"로 끝맺고 으뜸음 종지와 맞춘다.',
]

def main():
    selected=json.loads((HERE/'candidate-audit.json').read_text(encoding='utf-8'))['selected']
    out=HERE/'reviewed-baseline'
    if out.exists():raise FileExistsError(out)
    shutil.copytree(HERE/'candidates'/selected,out)
    comp=Composition.from_dict(json.loads((out/'piano/composition.json').read_text(encoding='utf-8')))
    first=audit_bundle(comp,out)
    cues=json.loads((out/'lyric-cues.json').read_text(encoding='utf-8'))
    assert len(cues)==len(REASONS)==12
    approvals=[dict(phrase_id='line_%02d'%(i+1),digest=first['phrase_digests']['line_%02d'%(i+1)],decision='accept',
                    reviewer='Claude agent editorial (no human listening label)',reason=r,waived_codes=[])
               for i,r in enumerate(REASONS)]
    (out/'editorial-review.json').write_text(json.dumps(approvals,ensure_ascii=False,indent=2),encoding='utf-8')
    log=[dict(phrase_id='line_%02d'%(i+1),text=c['text'],decision='accept',reason=r) for i,(c,r) in enumerate(zip(cues,REASONS))]
    (out/'lyric-review-log.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'feedback.json').write_text(json.dumps(dict(source='user feedback on previous test version',
        previous='retrofit lyrics on authored melody (dd commit 918b626)',
        user_comment='선율은 좋았는데 가사 문맥과 단어 선정들이 맞지 않는 느낌',
        this_version='lyric-first remake; unrated, awaiting user listening',used_as_training_preference=False),
        ensure_ascii=False,indent=2),encoding='utf-8')
    final=audit_bundle(comp,out)
    (out/'coherence-audit.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(selected=selected,accepted=final['accepted'],issues=len(final['issues']),
                          missing=final['editorial_missing']),ensure_ascii=False))
    assert final['accepted']

main()
