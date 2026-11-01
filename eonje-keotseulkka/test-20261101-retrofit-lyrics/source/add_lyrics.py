"""Add the authored Korean lyrics (one syllable per melody note) to the final score.

  python add_lyrics.py   (run from the omr-genre-bootstrap checkout with PYTHONPATH=src)
Reads final/score.musicxml, writes final-lyrics/score.musicxml + lyrics.txt. Notes are unchanged.
"""
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('compose_v2', HERE/'compose_v2.py')
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)

# bar index -> syllables (one Hangul character per melody note); intro and last bar instrumental
LYRICS = {
    4: '무대앞에', 5: '선너를', 6: '바라보던', 7: '날',
    8: '떨리는손', 9: '꼭잡고', 10: '사진한장', 11: '담아',
    12: '네이름이', 13: '불리던', 14: '특상이란', 15: '말에',
    16: '눈물고인', 17: '채로', 18: '손뼉쳤어', 19: '대견해',
    20: '언제이리', 21: '자랐니', 22: '작던아이', 23: '가',
    24: '오늘하루', 25: '가족과', 26: '함께라서', 27: '좋아',
    28: '고마워', 29: '사랑해', 30: '요',
}
LINES = [
    ('A', ['무대 앞에 선 너를 바라보던 날', '떨리는 손 꼭 잡고 사진 한 장 담아']),
    ('B', ['네 이름이 불리던 특상이란 말에', '눈물 고인 채로 손뼉 쳤어 대견해']),
    ("A'", ['언제 이리 자랐니 작던 아이가', '오늘 하루 가족과 함께라서 좋아']),
    ('Coda', ['고마워 사랑해요']),
]


def main():
    bars = [row for _, _, rows, _ in compose.SECTIONS for row in rows]
    placements = []
    for index, (_, notes) in enumerate(bars):
        if index not in LYRICS:
            continue
        sung, onset = [], 0
        for pitch, quarters in notes:
            if pitch is not None:
                sung.append((onset, pitch))
            onset += int(quarters*12)
        syllables = list(LYRICS[index])
        if len(syllables) != len(sung):
            raise ValueError('bar %d: %d syllables for %d notes' % (index+1, len(syllables), len(sung)))
        placements += [dict(bar=index, onset=o, pitch=p, lyric=s) for (o, p), s in zip(sung, syllables)]
    spec2 = importlib.util.spec_from_file_location('ballad', Path('scripts/generate_rich_piano_ballad.py'))
    ballad = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(ballad)
    root = ET.fromstring((HERE/'final'/'score.musicxml').read_text(encoding='utf-8'))
    ballad.add_lyrics(root, placements)
    out = HERE/'final-lyrics'
    out.mkdir(exist_ok=False)
    (out/'score.musicxml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(root, encoding='unicode'),
                                      encoding='utf-8')
    text = []
    for section, lines in LINES:
        text += ['['+section+']']+lines+['']
    (out/'lyrics.txt').write_text('\n'.join(text), encoding='utf-8')
    (out/'lyric-placements.json').write_text(json.dumps(placements, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(dict(syllables=len(placements))))


if __name__ == '__main__':
    main()
