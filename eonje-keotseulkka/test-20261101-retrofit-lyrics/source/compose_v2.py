"""'언제 이렇게 컸을까' v2 — authored melody + model-chosen accompaniment (2026-11-01).

Run from the omr-genre-bootstrap checkout with PYTHONPATH=src:
  python compose_v2.py --checkpoint <rich v1 best.pt> --output score-v2

The melody, chords, form and dynamics are composed here from the user's mood note
(original material, not taken from any existing song). Left-hand bass/arpeggio and
right-hand inner-voice pitches are chosen by the rich-piano v1 model through
scripts/generate_rich_piano_ballad.py:arrange_bar, under its playable-range rules.
The last bar is an authored tonic chord.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import torch

from omr.genres.contracts import Chord, Composition, ScoreEvent
from omr.genres.export import write_midi
from omr.genres.plans import build_plan
from omr.piano_music.export import piano_musicxml, read_piano_xml_events
from omr.piano_rich.train import load_checkpoint

_spec = importlib.util.spec_from_file_location('ballad', Path('scripts/generate_rich_piano_ballad.py'))
ballad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ballad)

TITLE = '언제 이렇게 컸을까'
SEED = 20261101
BPM = 72
R = None  # rest
# (section, story, [(chord root, [(pitch, quarters), ...]) per bar], melody velocity)
SECTIONS = [
    ('Intro', '콩쿠르 무대 앞, 조용한 설렘', [
        (0, [(67, 2), (72, 1), (71, 1)]),
        (9, [(69, 3), (64, 1)]),
        (5, [(65, 1), (69, 1), (72, 2)]),
        (7, [(71, 3), (R, 1)]),
    ], 58),
    ('A', '사진을 찍는 순간, 나란히 선 가족', [
        (0, [(64, 1), (67, 1), (72, 1.5), (71, .5)]),
        (7, [(71, 2), (74, 1), (71, 1)]),
        (9, [(72, 1.5), (71, .5), (69, 1), (64, 1)]),
        (4, [(67, 3), (R, 1)]),
        (5, [(65, 1), (69, 1), (72, 1), (77, 1)]),
        (0, [(76, 2), (72, 1), (67, 1)]),
        (2, [(69, 1.5), (72, .5), (74, 1), (72, 1)]),
        (7, [(71, 2), (67, 1), (R, 1)]),
    ], 66),
    ('B', '특상 — 대견하고 기특한 마음이 벅차오름', [
        (5, [(72, 1), (77, 1), (76, 1), (77, 1)]),
        (7, [(79, 2), (74, 1), (71, 1)]),
        (4, [(76, 1.5), (74, .5), (71, 1), (67, 1)]),
        (9, [(72, 3), (69, 1)]),
        (2, [(74, 1), (77, 1), (81, 1.5), (79, .5)]),
        (7, [(79, 2), (74, 2)]),
        (5, [(77, 1), (76, 1), (74, 1), (72, 1)]),
        (7, [(74, 2), (71, 1), (67, 1)]),
    ], 74),
    ("A'", '언제 이렇게 컸는지, 같은 선율을 다시 돌아봄', [
        (0, [(64, 1), (67, 1), (72, 1.5), (71, .5)]),
        (7, [(71, 2), (74, 1), (71, 1)]),
        (9, [(72, 1.5), (71, .5), (69, 1), (64, 1)]),
        (4, [(67, 3), (R, 1)]),
        (5, [(65, 1), (69, 1), (72, 1), (77, 1)]),
        (0, [(76, 2), (72, 1), (67, 1)]),
        (2, [(69, 1), (72, 1), (74, 1), (77, 1)]),
        (7, [(74, 2), (71, 2)]),
    ], 64),
    ('Coda', '가족 덕분에 행복한 하루', [
        (5, [(77, 2), (76, 1), (72, 1)]),
        (7, [(74, 2), (71, 1), (67, 1)]),
        (0, [(72, 4)]),
        (0, None),  # authored final tonic chord
    ], 56),
]
# arrange_bar picks texture from a bar index (chorus 16-27, quiet <4 or >=28); map this form onto it
# with multiples of 4 so the bar%2 / bar%4 accompaniment patterns are kept.
TEXTURE_BAR = {**{b: b for b in range(12)}, **{b: b+4 for b in range(12, 20)},
               **{b: b-12 for b in range(20, 28)}, **{b: b for b in range(28, 32)}}


def lead_events(bar, notes, velocity):
    events, onset = [], F(0)
    for pitch, quarters in notes:
        length = F(quarters).limit_denominator(4)
        if pitch is not None:
            events.append(ScoreEvent(bar, onset, length, 'piano_rh', pitch, velocity))
        onset += length
    assert onset == 4, (bar, onset)
    return events


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--checkpoint', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--seed', type=int, default=SEED)
    args = ap.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError('use a fresh output folder')
    torch.set_num_threads(2)
    model, tok, identity = load_checkpoint(args.checkpoint, 'cpu', allow_research=True)
    bars, labels = [], {}
    for name, story, rows, velocity in SECTIONS:
        labels[len(bars)] = name
        bars += [(root, notes, velocity) for root, notes in rows]
    assert len(bars) == 32
    chords = tuple(Chord(r, 'minor' if r in (2, 4, 9) else 'major') for r, _, _ in bars)
    plan = build_plan('딸의 콩쿠르 특상을 축하하는 가족의 따뜻한 하루', genre='ballad', mood='warm', bars=32,
                      bpm=BPM, seed=args.seed)
    plan = replace(plan, parts=('piano_rh', 'piano_lh'), chords=chords, bpm=BPM,
                   instruments={'piano_rh': 'acoustic_piano', 'piano_lh': 'acoustic_piano'})
    events, history, previous, reports = [], [], [], []
    for index, (chord, (root, notes, velocity)) in enumerate(zip(chords, bars)):
        if notes is None:
            for pitch, part, vel in [(36, 'piano_lh', 46), (48, 'piano_lh', 46), (60, 'piano_rh', 50),
                                     (64, 'piano_rh', 50), (67, 'piano_rh', 50), (72, 'piano_rh', 54)]:
                events.append(ScoreEvent(index, F(0), F(4), part, pitch, vel))
            reports.append(dict(bar=index, source='authored final tonic chord'))
            continue
        lead = lead_events(index, notes, velocity)
        rows, encoded, report = ballad.arrange_bar(model, tok, history, chord, TEXTURE_BAR[index], lead,
                                                   args.seed, previous)
        history.append(encoded)
        reports.append(dict(report, bar=index, texture_bar=TEXTURE_BAR[index],
                            source='authored melody; model-chosen LH and inner voices'))
        for r in rows:
            events.append(ScoreEvent(index, F(r['o'], 12), F(r['d'], 12), r['hand'], r['p'], r['v']))
    metadata = dict(title=TITLE, instrument='solo_piano', seed=args.seed, bpm=BPM, key='C major', meter='4/4',
                    usage_profile=identity.get('usage_profile'), form_labels=labels,
                    sections=[dict(name=n, story=s, bars=len(rows)) for n, s, rows, _ in SECTIONS],
                    user_input=dict(genre='미정 → 피아노 독주 발라드(작성자 선택)',
                                    mood='첫째 딸 콩쿠르 특상, 대견함·기특함, 언제 이렇게 컸는지, 가족 덕분에 행복한 하루'),
                    checkpoint_sha256=identity['checkpoint_sha256'],
                    note_source='authored original melody; rich-piano v1 model chooses LH and inner-voice pitches',
                    authored='melody, chords, form, section dynamics, accompaniment rhythm templates, final chord, title',
                    generation=reports,
                    limitations='The model does not read the photo or text; the scene mapping is authored. '
                                'No listening-quality claim.')
    c = Composition(plan, tuple(events), metadata)
    root = ET.fromstring(piano_musicxml(c, title=TITLE))
    first = root.find('part/measure')
    direction = ET.Element('direction', placement='above')
    ET.SubElement(ET.SubElement(direction, 'direction-type'), 'words').text = 'Dolce, cantabile — con pedale'
    first.insert(1, direction)
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(root, encoding='unicode')
    if sorted(read_piano_xml_events(xml)) != sorted((e.bar, e.onset, e.duration, e.pitch, e.part) for e in c.events):
        raise RuntimeError('grand-staff XML changed event timing')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'score.musicxml').write_text(xml, encoding='utf-8')
    write_midi(c, args.output/'score.mid')
    (args.output/'composition.json').write_text(json.dumps(c.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'provenance.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(bars=32, notes=len(events), xml_roundtrip=True,
                          skipped_slots=sum(r.get('skipped_unplayable_slots', 0) for r in reports))))


if __name__ == '__main__':
    main()
