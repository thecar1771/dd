"""Make the requested angry rap lyrics and piano backing from the trained piano model."""
import argparse
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

import torch
from omr.genres.contracts import Chord, Composition, ScoreEvent, Section, SongPlan
from omr.genres.export import musicxml, write_midi
from omr.genres.lyrics import _syllable_marks
from omr.piano_music.export import piano_musicxml, read_piano_xml_events
from omr.piano_music.train import load_checkpoint

TITLE = '한 판 더'
BPM, SEED = 96, 2026102807
VERSE1 = ['패배 창이 떠 내 표정은 굳어', '눈앞의 그 웃음에 열이 올라',
          '한 판 졌다고 내가 끝난 건가', '입꼬리 하나에 속이 뒤집혀',
          '쥔 손의 힘을 잠깐 풀어 놔', '심장은 빨라도 시선은 또렷해',
          '네가 누린 한 점 기억해 둘게', '다음 판의 답은 화면에 쓸게']
HOOK = ['비웃음은 짧아 내 연습은 길어', '한 판 더 가자 내 박자가 들려',
        '오늘 진 점수로 날 정하진 마', '말보다 플레이로 다시 보여 줄게']
VERSE2 = ['형광등 아래 번진 그 미소', '계속 떠올라도 내 손은 바빠',
          '놓친 타이밍을 하나씩 짚어', '운이란 핑계는 여기서 접어',
          '화를 박자로 바꿔 다시 눌러', '성급한 한 수는 이번엔 걸러',
          '이긴 네 실력도 인정은 할게', '그래서 더 재밌지 다음 판은 달라']


def rap_line(line, bar):
    marks = _syllable_marks(line)
    if not 1 <= len(marks) <= 15:
        raise ValueError('rewrite whole line, never truncate lyrics: ' + line)
    durations = [1] * len(marks)
    ends = [i for i, (_, mark) in enumerate(marks) if mark in ('single', 'end')]
    for extra in range(15 - len(marks)):
        durations[ends[-1 - extra % len(ends)]] += 1
    events, onset = [], 0
    for (syllable, mark), duration in zip(marks, durations):
        events.append(ScoreEvent(bar, F(onset, 4), F(duration, 4), 'vocal', None, 88,
                                 lyric=syllable, unpitched=True, syllabic=mark))
        onset += duration
    assert onset == 15
    return events


def minor_key(text):
    root = ET.fromstring(text)
    for key in root.findall('.//key'):
        key.find('fifths').text = '0'
        mode = key.find('mode')
        if mode is None:
            mode = ET.SubElement(key, 'mode')
        mode.text = 'minor'
    return root


@torch.inference_mode()
def learned_backing(model, tok, history, chord, bar):
    device = next(model.parameters()).device
    rng = torch.Generator(device=device).manual_seed(SEED + bar * 104729)
    prefix = tok.prefix('minor', 'romantic')
    current = [tok.ids['BAR'], tok.ids['LEN_48']]
    notes, sampled = [], 0
    hook = 12 <= bar < 16 or 24 <= bar < 28
    intro_outro = bar < 4 or bar >= 28
    # Authored boom-bap keyboard pulse; the trained piano model supplies RH
    # voicing and velocities. No claim that these weights learned rap music.
    slots = [(0, 9, 'lh', 0), (18, 6, 'lh', 7), (24, 9, 'lh', 0), (42, 6, 'lh', 7),
             (12, 6, 'rh', 0), (36, 6, 'rh', 0)]
    if hook:
        slots.append((30, 6, 'rh', 0))
    if intro_outro:
        slots = [s for s in slots if s[0] in (0, 12, 24)]
    pcs = {(chord.root + i) % 12 for i in (0, 3 if chord.quality == 'minor' else 4, 7)}

    def choose(candidates):
        nonlocal sampled
        if len(candidates) == 1:
            return candidates[0]
        kept = list(history)
        while len(prefix) + sum(map(len, kept)) + len(current) > model.config.max_sequence_length:
            kept.pop(0)
        context = prefix + [token for b in kept for token in b] + current
        logits = model(torch.tensor([context], device=device))[0, -1].float()
        indices = torch.tensor(candidates, device=device)
        probs = torch.softmax(logits[indices] / .72, dim=-1)
        assert torch.isfinite(probs).all()
        sampled += 1
        return indices[torch.multinomial(probs, 1, generator=rng)].item()

    for onset, duration, hand, degree in sorted(slots):
        previous = None
        for member in range(1 if hand == 'lh' else 2):
            current.extend([tok.ids[f'POS_{onset}'], tok.ids[f'DUR_{duration}']])
            if hand == 'lh':
                pitches = [36 + chord.root + degree]
                while pitches[0] > 55:
                    pitches[0] -= 12
            else:
                pool = [p for p in range(60, 76) if p % 12 in pcs]
                pitches = ([p for p in pool if any(p < q <= p + 12 for q in pool)] if member == 0
                           else [p for p in pool if previous < p <= previous + 12])
            pitch_token = choose([tok.ids[f'PITCH_{p}'] for p in pitches])
            current.append(pitch_token)
            pitch = int(tok.tokens[pitch_token].split('_')[-1])
            bins = range(8, 12) if hook else range(6, 9) if intro_outro else range(7, 11)
            velocity_token = choose([tok.ids[f'VELOCITY_{v}'] for v in bins])
            current.append(velocity_token)
            velocity = tok.decode_velocity(int(tok.tokens[velocity_token].split('_')[-1]))
            if hand == 'lh' and onset in (0, 24):
                velocity = min(104, velocity + 8)
            # Feed the exact final velocity bin in following context.
            current[-1] = tok.ids[f'VELOCITY_{tok.encode_velocity(velocity)}']
            notes.append([onset, duration, pitch, velocity])
            previous = pitch
    current.append(tok.ids['END_BAR'])
    row = dict(length=48, meter=[4, 4], notes=sorted(notes, key=lambda n: (n[0], n[2])))
    encoded = tok.encode_bar(row)
    return row, encoded, dict(bar=bar, sampled_choices=sampled, rhythm_source='authored sparse boom-bap piano groove')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checkpoint', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--image-sha256', required=True)
    args = ap.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError('preserve previous sample')
    torch.set_num_threads(8)
    model, tok, identity = load_checkpoint(args.checkpoint, 'cuda', allow_research=True)
    model.eval()
    roots = [9, 5, 2, 4] + [9, 9, 5, 4, 9, 9, 2, 4] + [9, 5, 2, 4] + [9, 9, 5, 4, 9, 9, 2, 4] + [9, 5, 2, 4] + [9, 5, 4, 9]
    chords = tuple(Chord(r, 'major' if r == 5 else 'minor') for r in roots)
    sections = (Section('intro', 0, 4, 1, 'rap', 'i'), Section('rap', 4, 8, 2, 'rap', 'v1'),
                Section('chorus', 12, 4, 3, 'rap', 'hook'), Section('rap', 16, 8, 2, 'rap', 'v2'),
                Section('chorus', 24, 4, 3, 'rap', 'hook'), Section('outro', 28, 4, 1, 'rap', 'o'))
    plan = SongPlan('rap', '게임 패배 뒤 눈앞의 웃음에 분노한 화자, 재대결로 향하는 랩',
                    'anger', 'ko', BPM, 32, SEED, sections, chords,
                    parts=('piano_rh', 'piano_lh'), groove='backbeat', texture='sparse', density=1,
                    instruments={'piano_rh': 'acoustic_piano', 'piano_lh': 'acoustic_piano'})
    bars, history, reports = [], [], []
    for bar, chord in enumerate(chords):
        if 24 <= bar < 28:
            row = deepcopy(bars[bar - 12])
            encoded = tok.encode_bar(row)
            report = dict(bar=bar, source='explicit hook reprise', source_bar=bar - 12)
        elif bar == 31:
            row = dict(length=48, meter=[4, 4], notes=[[0, 48, p, v] for p, v in [(45, 76), (52, 70), (60, 76), (64, 72), (69, 72)]])
            encoded = tok.encode_bar(row)
            report = dict(bar=bar, source='authored final A-minor tonic')
        else:
            row, encoded, report = learned_backing(model, tok, history, chord, bar)
        bars.append(row); history.append(encoded); reports.append(report)
        print(json.dumps({'bar': bar + 1, 'piano_notes': len(row['notes'])}), flush=True)
    metadata = dict(title=TITLE, user_mood='게임에서 후배에게 져서 화가 나고 분노함; 눈앞에서 비웃는다고 설명함',
                    image_observation='Smiling person indoors with ceiling lighting and an olive quilted jacket. Identity/intent not inferred.',
                    scene_policy='Game defeat, junior relationship and mockery come from user description, not inferred from face.',
                    image_sha256=args.image_sha256, image_not_copied=True,
                    key='A minor (natural minor)', genre='rap / boom-bap piano backing', bpm=BPM,
                    usage_profile='research-noncommercial',
                    checkpoint_sha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
                    note_source='fresh minor-conditioned inference from actual-score joint-piano model; RH voicings and velocities sampled',
                    rhythm_source='authored boom-bap piano pulse and LH root/fifth pattern; not learned rap genre',
                    lyric_source='new original Korean lyrics authored for this user story before assigning spoken-rhythm notes',
                    audio_scope='Piano backing only. Rap lyrics and rhythmic notation supplied; no synthesized human rap voice.',
                    form_labels={0: 'Intro', 4: 'Verse 1', 12: 'Hook', 16: 'Verse 2', 24: 'Hook', 28: 'Outro'},
                    generation=reports, model_condition={'mode': 'minor', 'style': 'romantic'}, seed=SEED)
    events = tuple(ScoreEvent(b, F(o, 12), F(d, 12), 'piano_lh' if p < 60 else 'piano_rh', p, v)
                   for b, row in enumerate(bars) for o, d, p, v in row['notes'])
    piano = Composition(plan, events, metadata)
    rap_events, lines = [], []
    for role, start, texts in [('Verse 1', 4, VERSE1), ('Hook', 12, HOOK), ('Verse 2', 16, VERSE2), ('Hook', 24, HOOK)]:
        for offset, text in enumerate(texts):
            bar = start + offset
            rap_events.extend(rap_line(text, bar))
            lines.append(dict(section=role, bar=bar, start_seconds=bar * 240 / BPM,
                              end_seconds=(bar + 1) * 240 / BPM, text=text))
    rap_plan = replace(plan, parts=('vocal',), instruments={'vocal': 'rap_voice'})
    rap = Composition(rap_plan, tuple(rap_events), metadata)
    full_plan = replace(plan, parts=('vocal', 'piano_rh', 'piano_lh'),
                        instruments={**plan.instruments, 'vocal': 'rap_voice'})
    full = Composition(full_plan, tuple(rap_events) + events, metadata)
    piano_root = minor_key(piano_musicxml(piano, title=TITLE + ' · Piano Backing'))
    full_root = deepcopy(piano_root)
    full_root.find('work/work-title').text = TITLE + ' · Rap & Piano'
    for field in full_root.findall('identification/miscellaneous/miscellaneous-field'):
        if field.get('name') == 'genre':
            field.text = 'rap_piano_backing'
    rap_root = ET.fromstring(musicxml(rap, title=TITLE))
    rap_sp = deepcopy(rap_root.find('part-list/score-part'))
    rap_part = deepcopy(rap_root.find('part'))
    for node in [rap_sp, rap_part, *rap_sp.iter(), *rap_part.iter()]:
        for attr in ('id',):
            if node.get(attr, '').startswith('P1'):
                node.set(attr, 'R1' + node.get(attr)[2:])
    rap_sp.find('part-name').text = 'Rap'
    rap_sp.find('part-abbreviation').text = 'Rap'
    rap_sp.find('score-instrument/instrument-name').text = 'Spoken rhythm'
    rap_sp.find('midi-instrument/midi-program').text = '116'
    rap_sp.find('midi-instrument/midi-channel').text = '6'
    for measure in rap_part.findall('measure'):
        for key in measure.findall('attributes/key'):
            measure.find('attributes').remove(key)
        for direction in list(measure.findall('direction')):
            measure.remove(direction)
    full_root.find('part-list').insert(0, rap_sp)
    full_root.insert(list(full_root).index(full_root.find('part')), rap_part)
    for folder, root, composition in [('piano', piano_root, piano), ('rap', full_root, full)]:
        out = args.output / folder
        out.mkdir(parents=True, exist_ok=True)
        text = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')
        (out / 'score.musicxml').write_text(text, encoding='utf-8')
        write_midi(composition, out / 'score.mid')
        (out / 'composition.json').write_text(json.dumps(composition.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    assert sorted(read_piano_xml_events(ET.tostring(piano_root, encoding='unicode'))) == sorted(
        (e.bar, e.onset, e.duration, e.pitch, e.part) for e in events)
    assert ''.join(n.text for n in full_root.findall('.//lyric/text')) == ''.join(l['text'].replace(' ', '') for l in lines)
    assert all(n.text == 'single' for n in full_root.findall('.//lyric/syllabic'))
    assert all(e.unpitched and e.pitch is None for e in rap_events)
    (args.output / 'provenance.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output / 'lyric-cues.json').write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding='utf-8')
    text = TITLE + '\n랩 / A단조 / 96 BPM / 4분의 4박자 / 32마디\n'
    previous = None
    lrc = []
    for line in lines:
        if previous != line['section']:
            text += '\n[' + line['section'] + ']\n'
            previous = line['section']
        text += line['text'] + '\n'
        seconds = line['start_seconds']
        lrc.append('[%02d:%05.2f]%s' % (int(seconds // 60), seconds % 60, line['text']))
    (args.output / 'lyrics.txt').write_text(text, encoding='utf-8')
    (args.output / 'lyrics.lrc').write_text('\n'.join(lrc) + '\n', encoding='utf-8')
    result = dict(title=TITLE, bars=32, bpm=BPM, seconds=80, piano_notes=len(events),
                  rap_syllables=len(rap_events), lyric_lines=len(lines), korean_hyphen_display='single',
                  piano_xml_roundtrip=True, whole_lyrics_preserved=True,
                  checkpoint_sha256=metadata['checkpoint_sha256'])
    (args.output / 'generation-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
