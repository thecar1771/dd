"""Recreate the photo-inspired, original Acoustic K-pop score with existing OMR models.

Run from the genre-bootstrap source checkout with PYTHONPATH=src. Checkpoints
are inputs, never downloaded by this script. Scene direction and lyrics are
authored here; the models sample notes and GMD-trained percussion respectively.
"""
import argparse
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import torch

from omr.genres.__main__ import write_outputs
from omr.genres.contracts import Chord, Composition, ScoreEvent
from omr.genres.generate import sample_bar
from omr.genres.lyrics import _syllable_marks
from omr.genres.plans import build_plan
from omr.genres.train import load_checkpoint as load_bootstrap
from omr.real_music.generate import sample_part_bar
from omr.real_music.notation import readable_composition
from omr.real_music.train import load_checkpoint as load_real

TITLE = '웃음이 번지는 순간 · Acoustic K-pop'
SEED = 2026102803
LINES = {
    'verse': ['낮은 불빛 아래 마주 앉아', '익숙한 하루에 웃음이 번져',
              '조용한 인사에 마음이 열려', '작은 이야기로 밤을 밝혀'],
    'chorus': ['네가 웃는 순간 빛이 켜져', '평범한 오늘이 노래가 되어'],
    'bridge': ['서두르지 않아도 괜찮아', '우리의 속도로 함께 걸어'],
}


def phrase_bars(line):
    """Split a full authored line at a word boundary, with balanced note budgets."""
    words = line.split()
    split = min(range(1, len(words)),
                key=lambda i: abs(sum(map(len, words[:i])) - sum(map(len, words[i:]))))
    return [_syllable_marks(' '.join(words[:split])), _syllable_marks(' '.join(words[split:]))]


def polish_notation(path, plan):
    """Add player-facing names and supplied chord symbols without changing notes."""
    root = ET.fromstring(path.read_text(encoding='utf-8'))
    names = ['Vocal', 'Piano RH', 'Piano LH', 'Bass (concert)', 'Drums']
    for node, name in zip(root.findall('part-list/score-part'), names):
        node.find('part-name').text = name
    for direction in root.findall('.//rehearsal'):
        direction.text = direction.text.title()
    pitch_names = {0: ('C', 0), 2: ('D', 0), 4: ('E', 0), 5: ('F', 0),
                   7: ('G', 0), 9: ('A', 0), 11: ('B', 0)}
    for measure, chord in zip(root.find('part').findall('measure'), plan.chords):
        step, alter = pitch_names[chord.root]
        harmony = ET.Element('harmony', placement='above')
        chord_root = ET.SubElement(harmony, 'root')
        ET.SubElement(chord_root, 'root-step').text = step
        if alter:
            ET.SubElement(chord_root, 'root-alter').text = str(alter)
        ET.SubElement(harmony, 'kind', text='m' if chord.quality == 'minor' else '').text = chord.quality
        index = next(i for i, child in enumerate(measure) if child.tag == 'note')
        measure.insert(index, harmony)
    path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode'), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bootstrap-checkpoint', type=Path, required=True)
    ap.add_argument('--rhythm-checkpoint', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError('Use a fresh output directory to preserve earlier scores')
    torch.set_num_threads(1)
    plan = build_plan('환한 미소와 따뜻한 실내 조명에서 영감을 받은 한국어 노래',
                      genre='kpop_acoustic', mood='warm', bars=32, bpm=88, seed=SEED)
    # The preset chose D major. Transpose the supplied harmony to accessible C major.
    chords = tuple(Chord((c.root - 2) % 12, c.quality) for c in plan.chords)
    plan = replace(plan, chords=chords[:-1] + (Chord(0, 'major'),))
    vocal_text = {bar: [] for bar in range(plan.bars)}
    lyric_lines = []
    for section_index, section in enumerate(plan.sections):
        bank = LINES.get(section.role)
        if not bank:
            continue
        for phrase_index, start in enumerate(range(section.start_bar, section.start_bar + section.bars, 2)):
            line = bank[phrase_index % len(bank)]
            first, second = phrase_bars(line)
            vocal_text[start], vocal_text[start + 1] = first, second
            lyric_lines.append(dict(section_index=section_index, section=section.role,
                                    start_bar=start, end_bar=start + 2, text=line,
                                    syllables=len(first) + len(second), first_note_in_group=0))

    model, tok, bootstrap_identity = load_bootstrap(args.bootstrap_checkpoint, torch.device('cpu'))
    events, note_reports, hooks = [], [], {}
    previous_pitch = None
    for bar in range(plan.bars):
        marks = vocal_text[bar]
        section = plan.section_at(bar)
        key = ((bar - section.start_bar) % 4, plan.chords[bar], tuple(marks))
        cached = hooks.get(key) if section.role == 'chorus' else None
        fixed = tuple(replace(e, bar=bar) for e in cached) if cached is not None else None
        sampled, report = sample_bar(model, tok, plan, bar, len(marks), previous_pitch=previous_pitch,
                                     seed=SEED + bar * 104729, temperature=0.72, fixed_vocal=fixed)
        vocal = [e for e in sampled if e.part == 'vocal']
        assert len(vocal) == len(marks)
        vocal = [replace(e, lyric=syllable, syllabic=mark) for e, (syllable, mark) in zip(vocal, marks)]
        if section.role == 'chorus' and cached is None:
            hooks[key] = vocal
        if vocal:
            previous_pitch = vocal[-1].pitch
        events.extend(vocal)
        events.extend(e for e in sampled if e.part not in ('vocal', 'drums'))
        note_reports.append(dict(bar=bar, **report))
        print(json.dumps({'stage': 'notes', 'bar': bar + 1}), flush=True)
    del model, tok

    model, tok, rhythm_identity = load_real(args.rhythm_checkpoint, 'cpu')
    assert not rhythm_identity['research_only']
    style_key = json.dumps(['gmd', 'pop', True, 0], separators=(',', ':'))
    assert style_key in rhythm_identity['trained_control_counts']
    rhythm_reports = []
    for bar in range(plan.bars):
        control = dict(source='gmd', style='pop', meter=[4, 4], bpm=plan.bpm, drum=True, program=0)
        row, report = sample_part_bar(model, tok, control, seed=SEED + 7 + bar * 104729,
                                      temperature=0.72, max_events=32)
        role = plan.section_at(bar).role
        factor = {'intro': 0.42, 'verse': 0.62, 'chorus': 0.82, 'bridge': 0.53, 'outro': 0.38}[role]
        events.extend(ScoreEvent(bar=bar, onset=Fraction(n[0], 12), duration=Fraction(n[1], 12),
                                 part='drums', pitch=n[2], velocity=max(25, min(100, round(n[3] * factor))),
                                 unpitched=True) for n in row['notes'])
        rhythm_reports.append(dict(bar=bar, **report))
        print(json.dumps({'stage': 'rhythm', 'bar': bar + 1}), flush=True)
    metadata = {
        'title': TITLE, 'seed': SEED, 'usage_profile': 'commercial-compatible', 'research_only': False,
        'scene_direction': 'Authored from the visible smile and warm indoor lighting; photo is not published.',
        'lyric_source': 'New original Korean lyrics authored before note sampling; no source song lyrics.',
        'lyric_lines': lyric_lines, 'lyrics_strategy': 'whole authored phrases split at word boundaries',
        'lyric_syllables_preserved': True,
        'plan_source': 'Explicit 32-bar Acoustic K-pop plan, 4/4, C major, quarter=88; not learned photo interpretation.',
        'note_source': 'Synthetic-trained conditional Transformer for vocal/piano/bass; real-source GMD-trained Transformer for drums.',
        'real_source_training': {'drums': True, 'vocal_piano_bass': False},
        'product_to_source_style_bridge': {'product_genre': 'kpop_acoustic', 'source_style': 'gmd/pop'},
        'bootstrap_checkpoint_sha256': hashlib.sha256(args.bootstrap_checkpoint.read_bytes()).hexdigest(),
        'rhythm_checkpoint_sha256': hashlib.sha256(args.rhythm_checkpoint.read_bytes()).hexdigest(),
        'rhythm_training_manifest_sha256': rhythm_identity['manifest_sha256'],
        'note_generation': note_reports, 'rhythm_generation': rhythm_reports,
        'arrangement_edits': 'Authored section-dependent drum velocity scaling; notation quantization separately recorded.',
        'limitations': 'Experimental score. Scene and lyric meaning are authored; no claim of learned K-pop vocal performance.',
    }
    performed = Composition(plan, tuple(events), metadata)
    readable = readable_composition(performed)
    assert [e for e in readable.events if e.part != 'drums'] == [e for e in performed.events if e.part != 'drums']
    metrics = write_outputs(readable, args.output, TITLE)
    polish_notation(args.output / 'score.musicxml', plan)
    (args.output / 'performed-composition.json').write_text(json.dumps(performed.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output / 'provenance.json').write_text(json.dumps(readable.metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'bars': plan.bars, 'parts': plan.parts,
                      'lyric_syllables': sum(len(m) for m in vocal_text.values()), 'metrics': metrics}, ensure_ascii=True))


if __name__ == '__main__':
    main()
