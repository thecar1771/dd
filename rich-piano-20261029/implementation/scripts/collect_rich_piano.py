"""Collect additional REAL solo-piano Humdrum scores and convert them to piano_music rows.

usage:
  python -I scripts/collect_rich_piano.py fetch <corpus_root>
  python -I scripts/collect_rich_piano.py candidates <corpus_root> <prior_pieces.jsonl.gz> <prior_policy_excludes.json>

Sources are pinned GitHub commits (codeload tarballs). Only .krn files plus top-level
license/readme files are extracted, with path-safety checks. Scores are parsed with a
self-contained **kern reader that keeps ties, chords, spine voices and actual measure
lengths, and rejects measures whose voices disagree in duration instead of repairing them.
No transposition, augmentation or performance data.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
import gzip
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import sys
import tarfile
import unicodedata
import urllib.request

SOURCES = [
    # name, owner, repo, commit, license, usage_profile
    dict(name='nifc_chopin_first_editions', owner='pl-wnifc', repo='humdrum-chopin-first-editions',
         commit='95dfb105c1669c72d10b04088566154f12d3dc1c', license='CC-BY-4.0',
         usage_profile='commercial-compatible',
         attribution='First Editions of Fryderyk Chopin\'s Music, Copyright 2017-2021 The Fryderyk Chopin Institute '
                     '(https://nifc.pl), https://chopinscores.org, https://github.com/pl-wnifc/humdrum-chopin-first-editions, CC BY 4.0'),
    dict(name='nifc_polish_scores', owner='pl-wnifc', repo='humdrum-polish-scores',
         commit='13ac964e0dd8bcd5fffd837169cbf653242c12e8', license='CC-BY-4.0',
         usage_profile='commercial-compatible',
         attribution='Polish Music Heritage in Open Access, Copyright 2019-2022 The Fryderyk Chopin Institute '
                     '(https://nifc.pl), https://polishscores.org, https://github.com/pl-wnifc/humdrum-polish-scores, CC BY 4.0'),
    dict(name='sapp_joplin', owner='craigsapp', repo='joplin',
         commit='ad0840eb97e89fac7e89a94325a3d7526b0dc200', license='CC-BY-NC-SA-4.0', usage_profile='research-noncommercial',
         attribution='A Digital Edition of Scott Joplin\'s Music, Copyright (C) 2004-2021 Craig Stuart Sapp, '
                     'https://github.com/craigsapp/joplin, CC BY-NC-SA 4.0'),
    dict(name='sapp_haydn_sonatas', owner='craigsapp', repo='haydn-piano-sonatas',
         commit='299abc8f11eed4982f9fcddf2fc519b7b50b6214', license='CC-BY-NC-SA-4.0', usage_profile='research-noncommercial',
         attribution='A digital edition of Haydn piano sonatas (Universal Edition 1901), Copyright (C) 2008-2021 '
                     'Craig Stuart Sapp, https://github.com/craigsapp/haydn-piano-sonatas, CC BY-NC-SA 4.0'),
]
TOP = {'LICENSE', 'LICENSE.txt', 'LICENSE.md', 'README.md', 'CITATION.cff', '.zenodo.json'}
TPQ = 12  # piano_music canonical ticks per quarter note


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def resolve_commit(owner, repo):
    api = f'https://api.github.com/repos/{owner}/{repo}'
    with urllib.request.urlopen(api, timeout=60) as r:
        branch = json.load(r)['default_branch']
    with urllib.request.urlopen(f'{api}/commits/{branch}', timeout=60) as r:
        return json.load(r)['sha']


def fetch(root):
    root = Path(root)
    cache, log = root / 'cache', root / 'audit' / 'fetch.jsonl'
    cache.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    pins = root / 'audit' / 'pins.json'
    pinned = json.loads(pins.read_text()) if pins.exists() else {}
    records = []
    for src in SOURCES:
        sha = src['commit'] or pinned.get(src['name']) or resolve_commit(src['owner'], src['repo'])
        pinned[src['name']] = sha
        pins.write_text(json.dumps(pinned, indent=1))
        tgz = cache / f"{src['repo']}-{sha}.tar.gz"
        url = f"https://codeload.github.com/{src['owner']}/{src['repo']}/tar.gz/{sha}"
        if not tgz.exists():
            part = tgz.with_suffix('.part')
            with urllib.request.urlopen(url, timeout=1200) as r, open(part, 'wb') as f:
                for block in iter(lambda: r.read(1 << 20), b''):
                    f.write(block)
            os.replace(part, tgz)
        dest = (root / 'raw' / src['name']).resolve()
        dest.mkdir(parents=True, exist_ok=True)
        extracted, unsafe = 0, []
        with tarfile.open(tgz, 'r:gz') as t:
            for m in t:
                if '/' not in m.name:
                    continue
                rel = m.name.split('/', 1)[1]
                if not rel or not (rel in TOP or rel.lower().endswith('.krn')):
                    continue
                norm = posixpath.normpath(rel)
                if (not m.isfile() or norm != rel or norm.startswith(('/', '..')) or '\\' in rel or ':' in rel):
                    unsafe.append(m.name)
                    continue
                out = (dest / Path(*norm.split('/'))).resolve()
                if not str(out).startswith(str(dest) + os.sep):
                    unsafe.append(m.name)
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                with t.extractfile(m) as fsrc, open(out, 'wb') as o:
                    o.write(fsrc.read())
                extracted += 1
        rec = dict(source=src['name'], owner=src['owner'], repo=src['repo'], commit=sha, tarball=url,
                   tarball_sha256=sha256_file(tgz), tarball_bytes=tgz.stat().st_size,
                   extracted_files=extracted, skipped_unsafe=unsafe)
        records.append(rec)
        print(json.dumps(rec), flush=True)
    log.write_text(''.join(json.dumps(r) + '\n' for r in records))


# --------------------------------------------------------------------------- **kern reader

RECIP = re.compile(r'(\d+)(?:%(\d+))?(\.*)')
PITCH = re.compile(r'([A-Ga-g])\1*([#\-n]*)')
PC = dict(c=0, d=2, e=4, f=5, g=7, a=9, b=11)


class KernError(ValueError):
    pass


def kern_duration(tok):
    m = RECIP.search(tok)
    if not m:
        return None
    digits, ratio, dots = m.groups()
    if set(digits) == {'0'}:
        base = Fraction(8 * 2 ** (len(digits) - 1))  # 0 = breve, 00 = long
    else:
        base = Fraction(4 * (int(ratio) if ratio else 1), int(digits))
    return base * (2 - Fraction(1, 2 ** len(dots)))


def kern_pitch(tok):
    m = PITCH.search(tok)
    if not m:
        return None
    letters = m.group(0)[:len(m.group(0)) - len(m.group(2))]
    # Kern signifiers are unordered (e.g. "8BB^^-L", "16b]-"): '#'/'-' anywhere are accidentals.
    octave = 3 + len(letters) if letters[0].islower() else 4 - len(letters)
    return 12 * (octave + 1) + PC[letters[0].lower()] + tok.count('#') - tok.count('-')


def parse_kern(text, trace=None):
    """Return reference records, absolute notes (quarters), barline times, meters and a report.

    Notes are [onset, duration, midi, staff, voice] with tied notes merged. Measures keep
    their actual (possibly partial) length; repeats stay in literal score order.
    """
    report = Counter()
    ref, spines, started = {}, None, False
    notes, active = [], {}
    barlines, meters, instruments = [], {}, set()
    meter, t = None, Fraction(0)
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if line.startswith('!!'):
            if line.startswith('!!!') and not line.startswith('!!!!'):
                key, _, value = line[3:].partition(':')
                ref.setdefault(key.strip(), value.strip())
            continue
        toks = line.split('\t')
        if not started:
            if not line.startswith('**'):
                raise KernError(f'line {lineno}: data before exclusive interpretation')
            spines = [dict(kind=tok, staff=None) for tok in toks]
            started = True
            kern = [i for i, s in enumerate(spines) if s['kind'] == '**kern']
            if not kern:
                raise KernError('no **kern spine')
            for order, i in enumerate(kern):
                spines[i]['staff'] = len(kern) - order  # Humdrum: lowest staff first
            for s in spines:
                s['busy'] = Fraction(0)
            continue
        if len(toks) != len(spines):
            raise KernError(f'line {lineno}: {len(toks)} tokens for {len(spines)} spines')
        if toks[0].startswith('*'):
            new, i = [], 0
            line_meter = None
            while i < len(toks):
                tok, s = toks[i], spines[i]
                if tok == '*^':
                    new += [dict(s), dict(s)]
                    i += 1
                elif tok == '*v':
                    j = i
                    while j < len(toks) and toks[j] == '*v':
                        j += 1
                    group = spines[i:j]
                    if len({g['busy'] for g in group}) > 1 and s['kind'] == '**kern':
                        report['merge_with_unequal_voice_time'] += 1
                    merged = dict(group[0], busy=max(g['busy'] for g in group))
                    new.append(merged)
                    i = j
                elif tok == '*-':
                    i += 1
                elif tok == '*x':
                    if i + 1 >= len(toks) or toks[i + 1] != '*x':
                        raise KernError(f'line {lineno}: unpaired *x')
                    new += [spines[i + 1], s]
                    i += 2
                elif tok == '*+' or tok.startswith('**'):
                    raise KernError(f'line {lineno}: spine addition unsupported')
                else:
                    if s['kind'] == '**kern':
                        m = re.match(r'^\*staff(\d+)', tok)
                        if m:
                            s['staff'] = int(m.group(1))
                        m = re.match(r'^\*M(\d+)/(\d+)$', tok)
                        if m and line_meter is None:
                            line_meter = (int(m.group(1)), int(m.group(2)))
                        if re.match(r'^\*I[a-z]', tok):
                            instruments.add(tok[2:])
                    new.append(s)
                    i += 1
            spines = new
            if line_meter:
                meter = line_meter
                meters[t] = meter
            if not spines:
                break
            continue
        if toks[0].startswith('!'):
            continue
        kern_ids = [i for i, s in enumerate(spines) if s['kind'] == '**kern']
        if toks[0].startswith('='):
            when = max(spines[i]['busy'] for i in kern_ids)
            when = max(when, t)
            for i in kern_ids:
                if spines[i]['busy'] < when:
                    report['underfull_voice_measures'] += 1
                    spines[i]['busy'] = when
            t = when
            if not barlines or barlines[-1] != t:
                barlines.append(t)
            continue
        staff_voices = defaultdict(list)
        for i in kern_ids:
            staff_voices[spines[i]['staff']].append(i)
        timed = graced = False
        for i in kern_ids:
            tok = toks[i]
            if tok == '.':
                continue
            s = spines[i]
            if s['busy'] > t:
                raise KernError(f'line {lineno}: new token while voice still sounding')
            voice = staff_voices[s['staff']].index(i)
            subs = [x for x in tok.split(' ') if x and x != '.']
            grace = [('q' in x or 'Q' in x) for x in subs]
            durs = [None if g else kern_duration(x) for x, g in zip(subs, grace)]
            first = next((d for d in durs if d is not None), None)
            if first is None:
                if subs and any(grace):
                    report['grace_notes_not_modeled'] += len(subs)
                    graced = True
                    continue
                raise KernError(f'line {lineno}: token without duration {tok!r}')
            if len({d for d in durs if d is not None}) > 1:
                report['chords_with_mixed_durations'] += 1
            for sub, g, dur in zip(subs, grace, durs):
                if g:
                    report['grace_notes_not_modeled'] += 1
                    continue
                if dur is None:
                    dur = first
                    report['chord_notes_inheriting_duration'] += 1
                if 'r' in sub:
                    continue
                pitch = kern_pitch(sub)
                if pitch is None:
                    report['pitchless_tokens_treated_as_spacers'] += 1
                    continue
                if not 21 <= pitch <= 108:
                    raise KernError(f'pitch {pitch} outside piano keyboard')
                key = (s['staff'], pitch)
                if ']' in sub or '_' in sub:
                    prior = active.get(key)
                    if prior is not None and prior[0] + prior[1] == t:
                        prior[1] += dur
                        report['tied_continuations_merged'] += 1
                        if ']' in sub:
                            active.pop(key, None)
                        continue
                    report['orphan_tie_continuations'] += 1
                note = [t, dur, pitch, s['staff'], voice]
                notes.append(note)
                if trace is not None:
                    trace.append((lineno, sub, note))
                if '[' in sub or '_' in sub:
                    active[key] = note
                else:
                    active.pop(key, None)
            s['busy'] = t + first
            timed = True
        if not timed and (graced or any(spines[i]['busy'] <= t for i in kern_ids)):
            continue  # zero-duration line: grace notes, or only non-note spines while a voice is due
        # Next line time: earliest end among sounding voices. A due voice holding a null
        # token (missing rest in the source) is treated as silent instead of stopping time.
        sounding = [spines[i]['busy'] for i in kern_ids if spines[i]['busy'] > t]
        if sounding:
            t = min(sounding)
        due_null = [i for i in kern_ids if toks[i] == '.' and spines[i]['busy'] < t]
        report['silent_voice_gaps_without_rest'] += bool(due_null and timed)
    if not started:
        raise KernError('empty file')
    end = max([t] + [n[0] + n[1] for n in notes])
    return dict(ref=ref, notes=notes, barlines=barlines, end=end, meters=meters,
                instruments=sorted(instruments), report=report,
                exclusive=sorted({s['kind'] for s in spines}) if spines else [])


def to_ticks(value, report, label):
    exact = value * TPQ
    if exact.denominator != 1:
        report[label] += 1
    return int((exact + Fraction(1, 2)) // 1)


def canonical_with_roles(events, report):
    """Same rule as omr.real_music.data.canonical_notes, keeping staff/voice per note."""
    by_pitch = defaultdict(dict)
    for onset, duration, pitch, staff, voice in events:
        prior = by_pitch[pitch].get(onset)
        if prior is None:
            by_pitch[pitch][onset] = [onset, duration, pitch, staff, voice]
        else:
            prior[1] = max(prior[1], duration)
            prior[3] = min(prior[3], staff)
            report['simultaneous_unisons_collapsed'] += 1
    result = []
    for pitch, positions in by_pitch.items():
        ordered = [positions[o] for o in sorted(positions)]
        for i, note in enumerate(ordered):
            if i + 1 < len(ordered) and note[0] + note[1] > ordered[i + 1][0]:
                note[1] = ordered[i + 1][0] - note[0]
                report['same_pitch_retriggers_trimmed'] += 1
            result.append(note)
    return sorted(result)


def kern_bars(parsed):
    """Convert parsed kern to piano_music bars plus parallel per-note role arrays."""
    report = Counter(parsed['report'])
    times = sorted(set([Fraction(0)] + parsed['barlines'] + [parsed['end']]))
    bounds = [to_ticks(x, report, 'quantized_barline_times') for x in times]
    starts = sorted(set(bounds))
    meter_times = sorted(parsed['meters'])
    events = []
    for onset, duration, pitch, staff, voice in parsed['notes']:
        a = to_ticks(onset, report, 'quantized_note_fields')
        b = to_ticks(onset + duration, report, 'quantized_note_fields')
        events.append([a, max(1, b - a), pitch, staff, voice])
    events = canonical_with_roles(events, report)
    bars = []
    for k in range(len(starts) - 1):
        length = starts[k + 1] - starts[k]
        idx = max([j for j, mt in enumerate(meter_times) if to_ticks(mt, Counter(), 'x') <= starts[k]], default=None)
        meter = list(parsed['meters'][meter_times[idx]]) if idx is not None else [4, 4]
        if idx is None:
            report['bars_without_declared_meter'] += 1
        if not 1 <= length <= 192:
            raise KernError(f'unrepresentable measure length {length} ticks')
        bars.append(dict(length=length, meter=meter, notes=[], staff=[], voice=[], tie=[]))
    end_tick = starts[-1]
    for onset, duration, pitch, staff, voice in events:
        end = min(onset + duration, end_tick)
        bar = max(j for j in range(len(bars)) if starts[j] <= onset)
        first = True
        while onset < end:
            stop = min(end, starts[bar + 1])
            b = bars[bar]
            b['notes'].append([onset - starts[bar], stop - onset, pitch, 72])
            b['staff'].append(staff)
            b['voice'].append(voice)
            b['tie'].append(0 if first else 1)
            if stop < end:
                report['cross_bar_held_note_splits'] += 1
            onset, bar, first = stop, bar + 1, False
    for b in bars:
        order = sorted(range(len(b['notes'])), key=lambda i: (b['notes'][i][0], b['notes'][i][2]))
        for key in ('notes', 'staff', 'voice', 'tie'):
            b[key] = [b[key][i] for i in order]
    report['empty_bars_retained'] = sum(not b['notes'] for b in bars)
    report['meter_changes'] = max(0, len(parsed['meters']) - 1)
    report['velocity_policy'] = '72: score has no per-note performed velocity; not inferred as a performance label'
    report['repeat_policy'] = 'literal score order, not unfolded repeat performance'
    report['tie_policy'] = 'kern ties merged per staff+key; re-split at barlines with note_tie_from_previous_bar=1'
    return bars, events, dict(report)


# --------------------------------------------------------------------------- candidate audit

CHOPIN_FILE = re.compile(r'^(\d{3})([a-z]*)(?:_([\w-]+?))?-(\d[a-z]*)-([A-Za-z]+)(?:-(\d{3}))?(?:-([a-z-]+))?\.krn$')
CHOPIN_EXCLUDE = {
    2: 'piano with orchestra (Variations on La ci darem)', 3: 'cello and piano', 8: 'piano trio',
    11: 'piano concerto', 13: 'piano with orchestra (Fantasy on Polish Airs)', 14: 'piano with orchestra (Krakowiak)',
    21: 'piano concerto', 22: 'piano with orchestra (Andante spianato and Grande polonaise)',
    65: 'cello sonata', 73: 'two pianos (Rondo op. 73)', 74: 'songs (voice and piano)'}
CHOPIN_SPECIAL = {'GDC': 'cello and piano (Grand Duo concertant)'}
FOUR_HANDS = re.compile(r'(?i)quatre[-_ ]mains|a[-_ ]4[-_ ]mains|na[-_ ]4[-_ ]r[eę]ce|4[-_ ]r[eę]ce|vierh[aä]ndig|four[-_ ]hands|4[-_ ]hands')
AUTHORITATIVE_COMPOSER = {'sapp_joplin': 'Joplin, Scott', 'sapp_haydn_sonatas': 'Haydn, Franz Joseph',
                          'nifc_chopin_first_editions': 'Chopin, Fryderyk'}
TIMING_AMBIGUITY = ('orphan_tie_continuations', 'underfull_voice_measures', 'merge_with_unequal_voice_time',
                    'silent_voice_gaps_without_rest', 'chords_with_mixed_durations', 'pitchless_tokens_treated_as_spacers')
ALLOWED_SPINES = {'**kern', '**dynam', '**fing', '**mod-dynam'}


def slug(text):
    text = str(text).replace('Ł', 'L').replace('ł', 'l')
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if c.isascii())
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def death_year(cdt):
    if not cdt or '-' not in cdt:
        return None
    tail = cdt.split('-', 1)[1] if not cdt.startswith('<') else cdt.rsplit('-', 1)[-1]
    if tail.startswith('>'):
        return None  # only "alive after"; death unknown
    m = re.search(r'(\d{4})', tail)
    return int(m.group(1)) if m else None


def fingerprint(events, n=6, limit=240):
    """Transposition-invariant top-line interval n-grams (near-duplicate detector)."""
    top = {}
    for onset, duration, pitch, *_ in events:
        top[onset] = max(top.get(onset, 0), pitch)
    line = [top[o] for o in sorted(top)][:limit]
    steps = [b - a for a, b in zip(line, line[1:])]
    return {tuple(steps[i:i + n]) for i in range(max(0, len(steps) - n + 1))}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def content_digest(bars):
    return hashlib.sha256(json.dumps([(b['length'], b['meter'], [n[:3] for n in b['notes']]) for b in bars],
                                     sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def existing_index(prior_path):
    rows = [json.loads(l) for l in gzip.open(prior_path, 'rt', encoding='utf-8')]
    index = dict(content=set(), chopin=set(), chopin_whole=set(), haydn=set(), joplin=set(),
                 groups={r['group']: r['split'] for r in rows}, prints=defaultdict(list))
    for r in rows:
        index['content'].add(r['content_sha256'])
        events = [[o + sum(b['length'] for b in r['bars'][:k]), d, p] for k, b in enumerate(r['bars'])
                  for o, d, p, v in b['notes']]
        index['prints'][r['group']].append((r['id'], fingerprint(events)))
        text = f"{r['work_key']} {r['title']}"
        if r['group'] == 'chopin':
            op = re.search(r'(?i)op(?:us)?\.?\s*(\d+)', text)
            if not op:
                continue
            no = (re.search(r'(?i)no\.?\s*(\d+)', text) or re.search(r'(?i)op \d+ (\d+)$', r['title'])
                  or re.search(r'Sonata \d (\d)(?:st|nd|rd|th)', r['title']))
            if no:
                index['chopin'].add((int(op.group(1)), int(no.group(1))))
            else:
                index['chopin_whole'].add(int(op.group(1)))
        elif r['group'] == 'haydn':
            m = re.search(r'sonata-(\d+)', r['work_key'])
            mv = re.search(r'(\d+)-(\d+)$', r['title'])
            if m and mv:
                index['haydn'].add((int(m.group(1)), int(mv.group(2))))
        elif r['group'] == 'joplin':
            index['joplin'].add(slug(r['title']).replace('-rag', '').replace('the-', ''))
    return index


def candidates(root, prior_path, excludes_path):
    root = Path(root).resolve()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    from omr.piano_music.data import composer_key as pm_group, normalize_key  # exactly as piano_music
    fetch_log = {r['source']: r for r in map(json.loads, (root / 'audit' / 'fetch.jsonl').read_text().splitlines())}
    withheld = {r['id'] for r in json.loads(Path(excludes_path).read_text(encoding='utf-8'))}
    prior = existing_index(prior_path)
    src_by_name = {s['name']: s for s in SOURCES}
    rows = []
    for name in ('nifc_chopin_first_editions', 'nifc_polish_scores', 'sapp_joplin', 'sapp_haydn_sonatas'):
        src, base = src_by_name[name], root / 'raw' / name
        for path in sorted(base.rglob('*.krn')):
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding='utf-8', errors='replace')
            row = dict(id=f"{name}:{path.stem}", source='nifc' if name.startswith('nifc') else 'humdrum',
                       corpus=name, raw_path=rel, sha256=sha256_file(path), source_commit=fetch_log[name]['commit'],
                       url=f"https://github.com/{src['owner']}/{src['repo']}/blob/{fetch_log[name]['commit']}/"
                           f"{path.relative_to(base).as_posix()}",
                       license=src['license'], usage_profile=src['usage_profile'], attribution=src['attribution'],
                       score_type='score encoding (Humdrum **kern), not performance MIDI', instrument='piano')
            ref = {}
            for l in text.splitlines():
                if l.startswith('!!!') and not l.startswith('!!!!'):
                    k, _, v = l[3:].partition(':')
                    ref.setdefault(k.strip(), v.strip())
            header = next((l for l in text.splitlines() if l.startswith('**')), '').split('\t')
            quick_inst = set(re.findall(r'(?:^|\t)\*I([a-z]+)', text, re.M))
            parsed = None
            if name != 'nifc_polish_scores' or (quick_inst and quick_inst <= {'piano', 'forte'}
                                                and header.count('**kern') >= 2):
                try:
                    parsed = parse_kern(text)
                except KernError as exc:
                    row['check_error'] = str(exc)
            composer = ref.get('COM') or ref.get('COM1') or ''
            if not composer and name in AUTHORITATIVE_COMPOSER:
                composer = AUTHORITATIVE_COMPOSER[name]
                row['composer_source'] = 'corpus identity (repository is a single-composer edition); no !!!COM record'
            cdt = ref.get('CDT') or ref.get('CDT1') or ''
            dy = death_year(cdt)
            for extra in ('CDT2',):
                if ref.get(extra):
                    d2 = death_year(ref[extra])
                    dy = max(dy, d2) if dy and d2 else None
            row.update(composer=composer, composer_dates=cdt, composer_death_year=dy,
                       composer_key=slug(composer.split(',')[0]) or 'unknown', piano_music_group=pm_group(composer),
                       title=ref.get('OTL', ''), genre=ref.get('AGN', ''), instrumentation=ref.get('AIN', ''),
                       license_record=ref.get('YEM', ''), publication=ref.get('PDT') or ref.get('PPR', ''),
                       shelfmark=ref.get('SMS-shelfmark') or ref.get('NIFC-shelfmark', ''))
            reason = None
            # ---- instrumentation / work identity
            if name == 'nifc_chopin_first_editions':
                row['composer_key'] = 'chopin'
                if dy is None and 'chopin' in composer.lower():
                    # NIFC files omit !!!CDT; Chopin's dates (1810-03-01 - 1849-10-17) are not in doubt.
                    dy, row['composer_death_year'] = 1849, 1849
                    row['composer_dates'] = '1810/03/01-1849/10/17 (documented; not in source record)'
                m = CHOPIN_FILE.match(path.name)
                special = path.name.split('-')[0]
                if m:
                    op, piece, part = int(m.group(1)), m.group(6), m.group(7)
                    no = re.search(r'(?i)no\.?\s*(\d+)', ref.get('rism-title', ''))
                    number = int(no.group(1)) if no else (int(piece) if piece else None)
                    row.update(opus=op, number=number, edition=m.group(4), publisher=m.group(5))
                    row['work_key'] = f'chopin:op{op}'
                    row['movement_key'] = f'chopin:op{op}' + (f'#{number}' if number else '')
                    if op in CHOPIN_EXCLUDE:
                        reason = f'not solo piano: {CHOPIN_EXCLUDE[op]}'
                    elif part and re.match(r'(violino|violoncello|violin|cello|piano|primo|secondo)', part):
                        reason = f'instrumental part file ({part}) of a chamber work'
                else:
                    lead = re.match(r'(\d{3})', path.name)
                    op = int(lead.group(1)) if lead else None
                    row['work_key'] = f'chopin:op{op}' if op else f'chopin:{slug(special)}'
                    row['movement_key'] = row['work_key'] + ('#' + slug(path.stem) if op else '')
                    row.update(opus=op, number=None, edition=None, publisher=None)
                    if op in CHOPIN_EXCLUDE:
                        reason = f'not solo piano: {CHOPIN_EXCLUDE[op]}'
                    elif op:
                        reason = 'unparsed edition filename for a numbered opus (needs manual movement vetting)'
                    if special in CHOPIN_SPECIAL:
                        reason = f'not solo piano: {CHOPIN_SPECIAL[special]}'
                if not reason and re.search(r'(?i)song|lied|concerto|trio', row['genre']):
                    reason = f"not solo piano: genre {row['genre']}"
            elif name == 'nifc_polish_scores':
                row['work_key'] = f"{row['composer_key']}:{slug(row['title'])[:60]}"
                row['movement_key'] = f"{row['work_key']}#{path.stem.split('_')[0]}"
                inst = quick_inst
                kern_n, spines = header.count('**kern'), set(header)
                if not inst or not inst <= {'piano', 'forte'}:
                    reason = f"not solo piano: instruments {sorted(inst) or 'undeclared'}"
                elif spines - ALLOWED_SPINES:
                    reason = 'texted or non-keyboard spine ' + ','.join(sorted(spines - ALLOWED_SPINES))
                elif FOUR_HANDS.search(path.name + ' ' + row['title']):
                    reason = 'four-hands piano'
                elif kern_n < 2:
                    reason = 'single-staff keyboard part (incomplete grand staff)'
                elif kern_n >= 4:
                    reason = 'four or more piano staves: possible four-hands / multi-player score'
            elif name == 'sapp_haydn_sonatas':
                hob = re.search(r'XVI:(\d+)', ref.get('SCT', ''))
                mv = re.match(r'(\d+)', ref.get('OMV', ''))
                row['work_key'] = f"haydn:keyboard-sonata-{int(hob.group(1)):02d}" if hob else f'haydn:{path.stem}'
                row['movement_key'] = row['work_key'] + (f"#{path.stem.split('-', 1)[1]}" if '-' in path.stem else '')
                row['composer_key'] = 'haydn'
                if hob and mv and (int(hob.group(1)), int(mv.group(1))) in prior['haydn']:
                    reason = 'duplicate movement already in final manifest (ASAP, same Hob. XVI number and movement)'
                    row['duplicate_of_movement'] = f"haydn:keyboard-sonata-{int(hob.group(1)):02d}#{mv.group(1)}"
            else:
                row['composer_key'] = 'joplin'
                key = slug(row['title']).replace('-rag', '').replace('the-', '')
                key = {'pine-apple': 'pineapple', 'sunflower-slow-drag': 'sun-flower-slow-drag',
                       'elite-syncopations': 'elite-syncopations', 'search-light': 'search-light',
                       'solace-a-mexican-serenade': 'solace'}.get(key, key)
                row['work_key'] = row['movement_key'] = f'joplin:{key}'
                if key in prior['joplin']:
                    reason = 'duplicate work already in final manifest (Mutopia Joplin, same title)'
            # ---- composition rights
            if not reason:
                if dy is None:
                    reason = 'withheld: composer death date unknown (underlying-composition rights unverified)'
                elif dy > 1955:
                    reason = f'withheld: composer died {dy} (composition may be protected, life+70)'
            if not reason and row['id'] in withheld:
                reason = 'previously withheld underlying-composition review'
            # ---- structural check with the independent reader
            if parsed is None and not reason:
                reason = f"conversion check failed: {row['check_error']}"
            if parsed is not None:
                try:
                    bars, events, report = kern_bars(parsed)
                    n_notes = sum(len(b['notes']) for b in bars)
                    row.update(n_measures=len(bars), n_notes=n_notes, n_tied_merged=report.get('tied_continuations_merged', 0),
                               check_report={k: v for k, v in report.items() if isinstance(v, int) and v},
                               content_sha256_unnormalized=content_digest(bars))
                    row['_print'] = fingerprint(events)
                    row['_events'] = len(events)
                    ambiguous = {k: report[k] for k in TIMING_AMBIGUITY if report.get(k)}
                    if not reason and ambiguous:
                        reason = 'timing/tie ambiguity excluded conservatively: ' + ', '.join(sorted(ambiguous))
                    if not reason and (len(bars) < 4 or n_notes < 32):
                        reason = 'fragment: fewer than 4 measures or 32 notes'
                    if not reason:
                        try:
                            normalize_key([dict(length=b['length'], meter=b['meter'], notes=b['notes']) for b in bars])
                        except ValueError as exc:
                            reason = f'key normalization rejected (same policy as base corpus): {exc}'
                except KernError as exc:
                    row['check_error'] = str(exc)
                    if not reason:
                        reason = f'conversion check failed: {exc}'
            row['reject_reason'] = reason
            rows.append(row)
    # ---- Chopin: one first edition per movement
    groups = defaultdict(list)
    for r in rows:
        if r['corpus'] == 'nifc_chopin_first_editions' and not r['reject_reason']:
            groups[r['movement_key']].append(r)
    for key, members in groups.items():
        members.sort(key=lambda r: (r['edition'] or '', r['raw_path']))
        keep = members[0]
        for other in members[1:]:
            other['reject_reason'] = 'alternate first edition of the same movement (version, not a new score)'
            other['duplicate_of'] = keep['id']
        op, no = keep['opus'], keep['number']
        if op is not None and (op in prior['chopin_whole'] or (op, no) in prior['chopin']):
            for r in members:
                r['reject_reason'] = r['reject_reason'] or 'duplicate movement already in final manifest (Chopin same opus/number)'
                r['duplicate_of_movement'] = f'chopin:op{op}' + (f'#{no}' if no else '')
    # ---- exact and near duplicates (against final manifest and within new candidates)
    accepted = [r for r in rows if not r['reject_reason']]
    seen_content = {}
    for r in accepted:
        c = r.get('content_sha256_unnormalized')
        if c in seen_content:
            r['reject_reason'] = 'exact duplicate content within new candidates'
            r['duplicate_of'] = seen_content[c]
        else:
            seen_content[c] = r['id']
    by_composer = defaultdict(list)
    for r in rows:
        if not r['reject_reason']:
            by_composer[r['composer_key']].append(r)
    for ck, members in by_composer.items():
        prior_prints = prior['prints'].get(ck, []) + prior['prints'].get(members[0]['piano_music_group'], [])
        kept = []
        for r in sorted(members, key=lambda r: r['id']):
            hit = next(((pid, jaccard(r['_print'], pp)) for pid, pp in prior_prints if jaccard(r['_print'], pp) >= .5), None)
            if hit:
                r['reject_reason'] = 'near-duplicate of final-manifest score (top-line interval 6-gram Jaccard >= 0.5)'
                r['duplicate_of'], r['similarity'] = hit[0], round(hit[1], 3)
                continue
            hit = next(((k['id'], jaccard(r['_print'], k['_print'])) for k in kept
                        if jaccard(r['_print'], k['_print']) >= .5), None)
            if hit:
                r['reject_reason'] = 'near-duplicate copy of another new candidate (same composer)'
                r['duplicate_of'], r['similarity'] = hit[0], round(hit[1], 3)
                continue
            kept.append(r)
    for r in rows:
        r['accepted'] = not r['reject_reason']
        r['composer_group'] = r['composer_key']
        r['frozen_split'] = prior['groups'].get(r['composer_key'], prior['groups'].get(r['piano_music_group']))
        r.pop('_print', None)
        r.pop('_events', None)
    out = root / 'candidates.jsonl'
    out.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows), encoding='utf-8')
    summary = summarize(rows)
    (root / 'audit' / 'candidates-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(summary['totals'], ensure_ascii=False))


def summarize(rows):
    acc = [r for r in rows if r['accepted']]
    per = {}
    for corpus in sorted({r['corpus'] for r in rows}):
        rs = [r for r in rows if r['corpus'] == corpus]
        a = [r for r in rs if r['accepted']]
        per[corpus] = dict(candidate_files=len(rs), accepted_files=len(a),
                           accepted_movements=len({r['movement_key'] for r in a}),
                           accepted_works=len({r['work_key'] for r in a}),
                           accepted_composers=len({r['composer_key'] for r in a}),
                           accepted_measures=sum(r.get('n_measures', 0) for r in a),
                           accepted_notes=sum(r.get('n_notes', 0) for r in a),
                           reject_reasons=Counter(re.sub(r'\[.*|: .*', '', r['reject_reason']) if not r['reject_reason'].startswith(('not solo', 'withheld')) else r['reject_reason'].split(' (')[0]
                                                  for r in rs if r['reject_reason']).most_common())
    return dict(totals=dict(candidate_files=len(rows), accepted_files=len(acc),
                            accepted_movements=len({r['movement_key'] for r in acc}),
                            accepted_works=len({r['work_key'] for r in acc}),
                            accepted_composers=len({r['composer_key'] for r in acc}),
                            accepted_measures=sum(r['n_measures'] for r in acc),
                            accepted_notes=sum(r['n_notes'] for r in acc),
                            by_usage_profile=Counter(r['usage_profile'] for r in acc),
                            by_frozen_split=Counter(str(r['frozen_split']) for r in acc)),
                per_corpus=per,
                accepted_by_composer=Counter(r['composer_key'] for r in acc).most_common())


# --------------------------------------------------------------------------- canonical rows

def style_for(row):
    if row['composer_key'] == 'joplin':
        return 'jazz'  # matches the existing Mutopia Joplin label
    born = re.match(r'[~<]?(\d{4})', row.get('composer_dates') or '')
    if born and int(born.group(1)) < 1775:
        return 'classical'
    return 'romantic'


def rows(root, prior_path):
    """Emit piano_music-compatible rows for accepted candidates, split by usage profile."""
    root = Path(root).resolve()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    from omr.piano_music.data import digest, normalize_key
    from omr.piano_music.tokenizer import PianoTokenizer
    from omr.real_music.data import canonical_notes
    tok = PianoTokenizer()
    prior_content = {json.loads(l)['content_sha256'] for l in gzip.open(prior_path, 'rt', encoding='utf-8')}
    cands = [json.loads(l) for l in (root / 'candidates.jsonl').read_text(encoding='utf-8').splitlines()]
    out_dir = root / 'rows'
    out_dir.mkdir(exist_ok=True)
    emitted, failures, stats = defaultdict(list), [], Counter()
    for cand in cands:
        if not cand['accepted']:
            continue
        try:
            parsed = parse_kern((root / cand['raw_path']).read_text(encoding='utf-8'))
            bars, events, report = kern_bars(parsed)
            plain = [[o, d, p, 72] for o, d, p, s, v in events]
            reference, _ = canonical_notes([[o, d, p, 72] for o, d, p, s, v in
                                            [[to_ticks(n[0], Counter(), 'x'),
                                              max(1, to_ticks(n[0] + n[1], Counter(), 'x') - to_ticks(n[0], Counter(), 'x')),
                                              n[2], n[3], n[4]] for n in parsed['notes']]])
            if sorted(plain) != sorted(reference):
                raise ValueError('role-preserving canonicalization differs from omr.real_music canonical_notes')
            normalized, keyinfo = normalize_key([dict(length=b['length'], meter=b['meter'], notes=b['notes']) for b in bars])
            out_bars, max_bar_tokens = [], 0
            for b, nb in zip(bars, normalized):
                ids = tok.encode_bar(dict(length=nb['length'], meter=nb['meter'], notes=nb['notes']))
                max_bar_tokens = max(max_bar_tokens, len(ids))
                out_bars.append(dict(length=nb['length'], meter=nb['meter'], notes=nb['notes'],
                                     note_staff=b['staff'], note_voice=b['voice'],
                                     note_tie_from_previous_bar=[bool(t) for t in b['tie']],
                                     note_attack=['held' if t else 'new' for t in b['tie']]))
            content = digest([(b['length'], b['meter'], [n[:3] for n in b['notes']]) for b in normalized])
            if content in prior_content:
                raise ValueError('exact normalized content already in final manifest')
            row = dict(id=cand['id'], source=cand['source'], corpus=cand['corpus'], composer=cand['composer'],
                       composer_dates=cand['composer_dates'], composer_key=cand['composer_key'],
                       piano_music_group=cand['piano_music_group'], frozen_split=cand['frozen_split'],
                       title=cand['title'], work_key=cand['work_key'], movement_key=cand['movement_key'],
                       license=cand['license'], usage_profile=cand['usage_profile'], attribution=cand['attribution'],
                       url=cand['url'], source_commit=cand['source_commit'], source_sha256=cand['sha256'],
                       raw_path=cand['raw_path'], instrument='piano', score_type=cand['score_type'],
                       mode=keyinfo['mode'], style=style_for(cand),
                       style_policy='coarse composer-period rule (Joplin: existing jazz label), not genre ground truth',
                       bars=out_bars, key_normalization=keyinfo, conversion=report,
                       role_policy='note_staff from Humdrum *staffN spine labels (1=upper); note_voice = sub-spine '
                                   'index within staff; not fingering or annotated hands',
                       max_bar_tokens_v1=max_bar_tokens, content_sha256=content, newly_collected=True)
            for key in ('opus', 'number', 'edition', 'publisher', 'shelfmark', 'publication'):
                if cand.get(key) not in (None, ''):
                    row[key] = cand[key]
            if not row['composer'] or row['piano_music_group'] in ('', 'unknown'):
                raise ValueError('empty composer identity')
            emitted[cand['usage_profile']].append(row)
            stats['rows'] += 1
            stats['notes'] += sum(len(b['notes']) for b in out_bars)
            stats['measures'] += len(out_bars)
            stats['held_note_segments'] += sum(map(sum, (b['note_tie_from_previous_bar'] for b in out_bars)))

        except Exception as exc:  # recorded, never silently dropped
            failures.append(dict(id=cand['id'], error=str(exc)))
    manifest = {}
    for profile, items in emitted.items():
        path = out_dir / f'pieces-{profile}.jsonl.gz'
        with gzip.open(path, 'wt', encoding='utf-8') as f:
            for r in items:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')
        manifest[path.name] = dict(rows=len(items), sha256=sha256_file(path),
                                   works=len({r['work_key'] for r in items}),
                                   composers=len({r['composer_key'] for r in items}),
                                   notes=sum(len(b['notes']) for r in items for b in r['bars']),
                                   measures=sum(len(r['bars']) for r in items))
    (out_dir / 'row-failures.json').write_text(json.dumps(failures, indent=1, ensure_ascii=False), encoding='utf-8')
    (out_dir / 'rows-summary.json').write_text(json.dumps(dict(files=manifest, totals=stats,
                                                              failures=len(failures)), indent=1), encoding='utf-8')
    print(json.dumps(dict(files=manifest, totals=stats, failures=len(failures))))


if __name__ == '__main__':
    if sys.argv[1] == 'rows':
        rows(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == 'candidates':
        candidates(*sys.argv[2:5])
    elif sys.argv[1] == 'fetch':
        fetch(sys.argv[2])
    else:
        raise SystemExit(__doc__)
