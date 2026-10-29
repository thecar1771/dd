"""Fresh-weight, texture-conditioned whole-corpus piano training with grouped held-out evaluation.

Example: python -m omr.piano_rich.train --manifest pieces.jsonl --output run
    --epochs 6 --batch-size 24 --device cuda --max-tokens 1536
No synthetic examples or arbitrary step budgets are used. Optional continuation
accepts only this same audited format and frozen source split assignments.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import asdict, fields
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import time
import unicodedata

import torch
from torch import nn

from omr.models.melody_transformer import MelodyTransformer, MelodyTransformerConfig
from .tokenizer import FORMAT, PianoTokenizer

CHECKPOINT_FORMAT = 'omr-rich-piano-checkpoint-v1'
SOURCES = frozenset(('mutopia', 'asap', 'dcml', 'humdrum', 'nifc'))
SPLITS = ('train', 'validation', 'test')
COMMERCIAL_LICENSES = frozenset(('cc0', 'cc0-1.0', 'public-domain', 'public domain',
                               'pd', 'cc-by-4.0', 'cc-by-sa-4.0', 'cc-by-3.0', 'cc-by-sa-3.0'))


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def source_hashes():
    """Normalize checkout line endings so Linux execution matches Windows code."""
    root = Path(__file__).parents[1]
    paths = [Path(__file__), Path(__file__).with_name('tokenizer.py'),
             Path(__file__).with_name('__init__.py'), root/'models'/'melody_transformer.py', root/'piano_music'/'tokenizer.py']
    return {p.relative_to(root).as_posix(): hashlib.sha256(
        p.read_text(encoding='utf-8').replace('\r\n', '\n').encode()).hexdigest() for p in paths}


def _group(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(value)).lower())


def _commercial(piece):
    # ASAP's dataset-level research restriction overrides the underlying score.
    return (piece['source'] in ('mutopia', 'dcml', 'nifc')
            and piece.get('usage_profile') == 'commercial-compatible'
            and str(piece.get('license', '')).strip().lower() in COMMERCIAL_LICENSES)


def _piano_marker(piece):
    if piece.get('drum') or piece.get('is_drum') or piece.get('piano_only') is False:
        raise ValueError('input must be piano only')
    for key in ('instrument', 'instrumentation', 'instruments', 'part', 'parts'):
        if key in piece:
            values = piece[key] if isinstance(piece[key], list) else [piece[key]]
            if not values or any(str(v).strip().lower() not in
                                 ('piano', 'solo piano', 'solo-piano', 'acoustic grand piano') for v in values):
                raise ValueError(f'non-piano marker {key}: {piece[key]!r}')
    for key in ('program', 'programs'):
        if key in piece:
            values = piece[key] if isinstance(piece[key], list) else [piece[key]]
            if any(isinstance(v, bool) or not isinstance(v, int) or v != 0 for v in values):
                raise ValueError('only acoustic piano MIDI program 0 is allowed')


def _fingerprints(piece):
    bars = []
    for bar in piece['bars']:
        notes = sorted((list(n[:3]) for n in bar['notes']), key=lambda n: (n[0], n[2]))
        bars.append([bar['length'], notes])
    base = next((n[2] for _, notes in bars for n in notes), 0)
    relative = [[length, [[o, d, p-base] for o, d, p in notes]] for length, notes in bars]
    return canonical_hash(bars), canonical_hash(relative)


def read_manifest(path, usage_profile='research-noncommercial'):
    """Validate provenance and conservative composer/work/content split isolation."""
    if usage_profile not in ('research-noncommercial', 'commercial-compatible'):
        raise ValueError('unsupported usage profile')
    tok = PianoTokenizer()
    pieces, ids, ownership = [], set(), {}
    with Path(path).open(encoding='utf-8-sig') as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                piece = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'nonfinite {value}')))
                if not isinstance(piece, dict):
                    raise ValueError('piece must be an object')
                for key in ('id', 'source', 'composer', 'work_key', 'split', 'license'):
                    if not isinstance(piece.get(key), str) or not piece[key].strip():
                        raise ValueError(f'missing or empty {key}')
                if piece['source'] not in SOURCES:
                    raise ValueError(f"unsupported source {piece['source']!r}")
                if piece['split'] not in SPLITS:
                    raise ValueError('split must be train, validation, or test')
                if piece['id'] in ids:
                    raise ValueError(f"duplicate piece id {piece['id']}")
                ids.add(piece['id'])
                piece.setdefault('usage_profile', 'research-noncommercial')
                if piece['usage_profile'] not in ('research-noncommercial', 'commercial-compatible'):
                    raise ValueError('unsupported piece usage_profile')
                if usage_profile == 'commercial-compatible' and not _commercial(piece):
                    raise ValueError('source/license/profile is not strictly commercial-compatible')
                _piano_marker(piece)
                # Validate the source once, including empty bars and note overlap.
                tok.encode_piece(piece)
                composer = _group(piece.get('composer_group', piece['composer']))
                groups = [('composer', composer), ('work', composer+':'+_group(piece['work_key']))]
                for key in ('group', 'split_group', 'work_group'):
                    if piece.get(key) is not None:
                        groups.append((key, str(piece[key])))
                exact, relative = _fingerprints(piece)
                groups.extend([('exact-content', exact), ('relative-content', relative)])
                for key in groups:
                    if key in ownership and ownership[key] != piece['split']:
                        raise ValueError(f'split leakage for {key[0]} {key[1]!r}')
                    ownership[key] = piece['split']
                pieces.append(piece)
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f'manifest line {line_number}: {exc}') from exc
    if not pieces:
        raise ValueError('manifest is empty')
    return pieces


def collate(sequences, device='cpu', pad_id=0):
    size = max(len(ids) for ids, _ in sequences)
    inputs = torch.full((len(sequences), size-1), pad_id, dtype=torch.long, device=device)
    targets = torch.full_like(inputs, -100)
    for row, (ids, mask) in enumerate(sequences):
        inputs[row, :len(ids)-1] = torch.tensor(ids[:-1], device=device)
        labels = [token if yes else -100 for token, yes in zip(ids[1:], mask[1:])]
        targets[row, :len(labels)] = torch.tensor(labels, device=device)
    return inputs, targets


def without_context(sequences, tok):
    """Evaluate each targeted bar with only BOS/MODE/STYLE, keeping targets fixed."""
    result = []
    for ids, mask in sequences:
        start = None
        for index in range(3, len(ids)):
            if ids[index] == tok.ids['BAR']:
                start = index
            if ids[index] == tok.ids['END_BAR'] and start is not None and mask[index]:
                bar = ids[start:index+1]
                # Rich header conditions are supplied, never scored. Retain the
                # same exact target mask when removing previous-bar context.
                result.append((ids[:3]+bar, [False]*3+mask[start:index+1]))
        if ids[-1] == tok.ids['EOS'] and mask[-1]:
            tokens, target_mask = result[-1]
            tokens.append(tok.ids['EOS'])
            target_mask.append(True)
    return result


def _autocast(device, precision):
    return torch.autocast(device_type='cuda', dtype=torch.bfloat16) if precision == 'bf16' else nullcontext()


@torch.inference_mode()
def evaluate(model, sequences, device='cpu', batch_size=24, tokenizer=None, precision='float32'):
    tok = tokenizer or PianoTokenizer()
    model.eval()
    loss_sum, count, correct = 0.0, 0, 0
    stage_count = {stage: 0 for stage in ('POS', 'DUR', 'PITCH', 'VELOCITY', 'ROLE', 'ATTACK')}
    stage_correct = dict(stage_count)
    stage_lookup = torch.full((len(tok.tokens),), -1, dtype=torch.long, device=device)
    for index, name in enumerate(tok.tokens):
        if name.split('_')[0] in stage_count:
            stage_lookup[index] = list(stage_count).index(name.split('_')[0])
    for offset in range(0, len(sequences), batch_size):
        x, y = collate(sequences[offset:offset+batch_size], device, tok.pad_id)
        with _autocast(device, precision):
            logits = model(x)
            loss = nn.functional.cross_entropy(logits.float().flatten(0, 1), y.flatten(),
                                               ignore_index=-100, reduction='sum')
        valid = y.ne(-100)
        hits = logits.argmax(-1).eq(y) & valid
        loss_sum += float(loss)
        count += int(valid.sum())
        correct += int(hits.sum())
        stages = stage_lookup[y.clamp_min(0)]
        for index, stage in enumerate(stage_count):
            selected = valid & stages.eq(index)
            stage_count[stage] += int(selected.sum())
            stage_correct[stage] += int((hits & selected).sum())
    if not count or not math.isfinite(loss_sum):
        raise ValueError('evaluation requires nonempty finite targets')
    return dict(loss=loss_sum/count, perplexity=math.exp(min(loss_sum/count, 700)),
                target_count=count, correct_count=correct, next_token_accuracy=correct/count,
                note_stage_accuracy={stage: dict(target_count=stage_count[stage],
                    correct_count=stage_correct[stage], accuracy=stage_correct[stage]/stage_count[stage]
                    if stage_count[stage] else None) for stage in stage_count})


def _write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                                    allow_nan=False)+'\n', encoding='utf-8')
    temporary.replace(path)


def _save_checkpoint(path, model, identity):
    temporary = Path(path).with_suffix('.pt.tmp')
    torch.save(dict(format=CHECKPOINT_FORMAT, model_config=asdict(model.config),
                    tokenizer_format=FORMAT, tokens=PianoTokenizer().tokens,
                    identity=identity, state_dict=model.state_dict()), temporary)
    temporary.replace(path)


def load_checkpoint(path, device='cpu', allow_research=False):
    """Load only this exact vocabulary/architecture/source version, with NC opt-in."""
    payload = torch.load(path, map_location='cpu', weights_only=True)
    tok = PianoTokenizer()
    if not isinstance(payload, dict) or payload.get('format') != CHECKPOINT_FORMAT:
        raise ValueError('unsupported piano checkpoint format')
    if payload.get('tokenizer_format') != FORMAT or payload.get('tokens') != tok.tokens:
        raise ValueError('incompatible piano tokenizer vocabulary')
    identity = payload.get('identity')
    if not isinstance(identity, dict) or identity.get('format') != CHECKPOINT_FORMAT:
        raise ValueError('missing checkpoint identity')
    profile = identity.get('usage_profile')
    if profile not in ('commercial-compatible', 'research-noncommercial'):
        raise ValueError('missing checkpoint usage profile')
    if profile == 'research-noncommercial' and not allow_research:
        raise ValueError('research-noncommercial checkpoint requires allow_research=True')
    if not identity.get('provenance') or any(p.get('source') not in SOURCES for p in identity['provenance']):
        raise ValueError('unsupported checkpoint training source')
    if profile == 'commercial-compatible' and not all(_commercial(p) for p in identity['provenance']):
        raise ValueError('checkpoint source/license/profile is not commercial-compatible')
    if identity.get('source_hashes') != source_hashes():
        raise ValueError('training-source hashes differ from compatible implementation')
    config = payload.get('model_config')
    if not isinstance(config, dict) or set(config) != {field.name for field in fields(MelodyTransformerConfig)}:
        raise ValueError('incompatible architecture fields')
    if (config.get('vocab_size') != len(tok.tokens) or config.get('pad_id') != tok.pad_id
            or config != identity.get('model_config')):
        raise ValueError('incompatible architecture/vocabulary identity')
    try:
        model = MelodyTransformer(MelodyTransformerConfig(**config))
        model.load_state_dict(payload['state_dict'], strict=True)
        model.to(device).eval()
    except (RuntimeError, TypeError, KeyError, ValueError) as exc:
        raise ValueError(f'incompatible piano architecture/state: {exc}') from exc
    identity = dict(identity, checkpoint_sha256=file_hash(path))
    return model, tok, identity


def train(manifest, output, *, epochs=6, batch_size=24, device='cuda', max_tokens=2048,
          context_bars=4, d_model=256, num_layers=6, nhead=8, dim_feedforward=1024,
          dropout=0.1, learning_rate=3e-4, weight_decay=0.01, seed=20261029,
          usage_profile='research-noncommercial', precision=None, checkpoint_every=1,
          progress_seconds=60.0, checkpoint_seconds=300.0, initial_checkpoint=None):
    started = time.monotonic()
    output, manifest = Path(output), Path(manifest)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('output must be an empty or nonexistent directory; refusing nonempty output')
    if epochs < 1 or batch_size < 1 or checkpoint_every < 1:
        raise ValueError('epochs, batch_size, checkpoint_every must be positive')
    if not all(math.isfinite(v) and v > 0 for v in (learning_rate, progress_seconds, checkpoint_seconds)):
        raise ValueError('learning rate/progress/checkpoint intervals must be finite and positive')
    if not math.isfinite(weight_decay) or weight_decay < 0 or not 0 <= dropout < 1:
        raise ValueError('invalid weight decay or dropout')
    # Set before any CUDA initialization; required by deterministic CUDA GEMMs.
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    device = torch.device(device)
    precision = precision or ('bf16' if device.type == 'cuda' else 'float32')
    if precision not in ('bf16', 'float32') or (precision == 'bf16' and device.type != 'cuda'):
        raise ValueError('bf16 precision requires CUDA; CPU uses float32')
    if device.type == 'cuda' and (not torch.cuda.is_available() or
            (precision == 'bf16' and not torch.cuda.is_bf16_supported())):
        raise ValueError('requested CUDA/bf16 device is unavailable')
    random.seed(seed)
    torch.manual_seed(seed)
    if device.type == 'cuda':
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    pieces = read_manifest(manifest, usage_profile)
    tok = PianoTokenizer()
    sequences, split_pieces, sequence_files, counts = {}, {}, {}, {}
    for split in SPLITS:
        selected = [p for p in pieces if p['split'] == split]
        if not selected:
            raise ValueError(f'manifest requires nonempty {split} split')
        split_pieces[split] = selected
        sequences[split], sequence_files[split] = [], []
        for p in selected:
            windows = tok.windows(p, max_tokens, context_bars)
            sequences[split].extend(windows)
            sequence_files[split].extend([p['id']]*len(windows))
        counts[split] = dict(files=len(selected), works=len({(_group(p['composer']), p['work_key']) for p in selected}),
            composers=len({_group(p['composer']) for p in selected}),
            bars=sum(len(p['bars']) for p in selected), notes=sum(len(b['notes']) for p in selected for b in p['bars']),
            empty_bars=sum(not b['notes'] for p in selected for b in p['bars']),
            source_counts={s: sum(p['source'] == s for p in selected) for s in sorted(SOURCES)},
            windows=len(sequences[split]), input_tokens=sum(len(ids)-1 for ids, _ in sequences[split]),
            target_tokens=sum(sum(mask) for _, mask in sequences[split]), file_ids=[p['id'] for p in selected])
    config = MelodyTransformerConfig(vocab_size=len(tok.tokens), d_model=d_model, nhead=nhead,
        num_layers=num_layers, dim_feedforward=dim_feedforward, dropout=dropout,
        max_sequence_length=max_tokens, pad_id=tok.pad_id)
    model = MelodyTransformer(config).to(device)
    initial_identity = None
    if initial_checkpoint is not None:
        prior, prior_tok, prior_identity = load_checkpoint(initial_checkpoint, device,
            allow_research=usage_profile == 'research-noncommercial')
        if prior.config != config or prior_tok.tokens != tok.tokens:
            raise ValueError('continuation architecture/vocabulary must be identical')
        current_splits = {p['id']: p['split'] for p in pieces}
        prior_splits = prior_identity.get('split_ownership')
        if not prior_splits or any(current_splits.get(k) != v for k, v in prior_splits.items()):
            raise ValueError('continuation source missing or frozen split changed')
        model.load_state_dict(prior.state_dict(), strict=True)
        initial_identity = {k: prior_identity[k] for k in
            ('checkpoint_sha256', 'manifest_sha256', 'epoch', 'optimizer_steps', 'usage_profile')}
        del prior
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    params = dict(epochs=epochs, batch_size=batch_size, device=str(device), max_tokens=max_tokens,
        context_bars=context_bars, learning_rate=learning_rate, weight_decay=weight_decay,
        seed=seed, precision=precision, usage_profile=usage_profile,
        checkpoint_every=checkpoint_every, progress_seconds=progress_seconds,
        checkpoint_seconds=checkpoint_seconds, model_config=asdict(config),
        initial_checkpoint=str(initial_checkpoint) if initial_checkpoint is not None else None)
    identity = dict(format=CHECKPOINT_FORMAT, tokenizer_format=FORMAT,
        manifest_sha256=file_hash(manifest), source_hashes=source_hashes(),
        usage_profile=usage_profile, model_config=asdict(config), params=params,
        parameter_count=sum(p.numel() for p in model.parameters()), fresh_initialization=initial_checkpoint is None,
        initial_checkpoint=initial_identity, split_ownership={p['id']: p['split'] for p in pieces},
        provenance=[{key: p[key] for key in ('id', 'source', 'license', 'usage_profile')} for p in pieces])
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output/'run.json', dict(identity=identity, dataset=counts))
    history, best_loss, best_epoch, steps = [], float('inf'), None, 0
    last_progress = last_checkpoint = time.monotonic()
    for epoch in range(1, epochs+1):
        order = list(range(len(sequences['train'])))
        random.Random(seed+epoch).shuffle(order)
        model.train()
        seen_files, seen_windows, seen_tokens, seen_input_tokens, loss_sum = set(), 0, 0, 0, 0.0
        epoch_started = time.monotonic()
        for start in range(0, len(order), batch_size):
            indices = order[start:start+batch_size]
            batch = [sequences['train'][i] for i in indices]
            x, y = collate(batch, device, tok.pad_id)
            optimizer.zero_grad(set_to_none=True)
            with _autocast(device, precision):
                logits = model(x)
                loss = nn.functional.cross_entropy(logits.float().flatten(0, 1), y.flatten(), ignore_index=-100)
            if not bool(torch.isfinite(loss)):
                raise ValueError(f'nonfinite training loss at epoch {epoch}, step {steps}')
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
            optimizer.step()
            steps += 1
            target_count = int(y.ne(-100).sum())
            loss_sum += float(loss.detach())*target_count
            seen_tokens += target_count
            seen_input_tokens += sum(len(ids)-1 for ids, _ in batch)
            seen_windows += len(batch)
            seen_files.update(sequence_files['train'][i] for i in indices)
            now = time.monotonic()
            progress = dict(epoch=epoch, optimizer_steps=steps, seen_windows=seen_windows,
                seen_target_tokens=seen_tokens, seen_input_tokens=seen_input_tokens,
                seen_files=sorted(seen_files), total_train_windows=len(order),
                walltime_seconds=now-started, train_loss_so_far=loss_sum/seen_tokens)
            if now-last_progress >= progress_seconds:
                _write_json(output/'progress.json', progress)
                with (output/'progress.jsonl').open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(progress, allow_nan=False)+'\n')
                print(json.dumps(progress), flush=True)
                last_progress = now
            if now-last_checkpoint >= checkpoint_seconds:
                _save_checkpoint(output/'progress.pt', model, dict(identity, epoch=epoch,
                    optimizer_steps=steps, epoch_complete=False, coverage=progress))
                last_checkpoint = now
        if seen_windows != counts['train']['windows'] or seen_tokens != counts['train']['target_tokens']:
            raise RuntimeError('epoch failed complete training coverage invariant')
        validation = evaluate(model, sequences['validation'], device, batch_size, tok, precision)
        entry = dict(epoch=epoch, optimizer_steps=steps, seen_files=sorted(seen_files),
            seen_windows=seen_windows, seen_target_tokens=seen_tokens, seen_input_tokens=seen_input_tokens,
            train_loss=loss_sum/seen_tokens, validation=validation,
            walltime_seconds=time.monotonic()-epoch_started)
        history.append(entry)
        checkpoint_identity = dict(identity, epoch=epoch, optimizer_steps=steps,
                                   epoch_complete=True, coverage=entry)
        _save_checkpoint(output/'final.pt', model, checkpoint_identity)
        if epoch % checkpoint_every == 0:
            _save_checkpoint(output/f'epoch-{epoch:04d}.pt', model, checkpoint_identity)
        if validation['loss'] < best_loss:
            best_loss, best_epoch = validation['loss'], epoch
            _save_checkpoint(output/'best.pt', model, checkpoint_identity)
        _write_json(output/'progress.json', dict(entry, best_epoch=best_epoch,
                                                total_walltime_seconds=time.monotonic()-started))
        _write_json(output/'epochs.json', history)
        print(json.dumps(entry, allow_nan=False), flush=True)
    # Free the final training model before constructing and testing the selected model.
    del optimizer, model, logits, loss
    if device.type == 'cuda':
        torch.cuda.empty_cache()
    best, _, selected_identity = load_checkpoint(output/'best.pt', device, allow_research=True)
    metrics = {}
    for split in ('validation', 'test'):
        metrics[split] = evaluate(best, sequences[split], device, batch_size, tok, precision)
        metrics[split+'_without_context'] = evaluate(best, without_context(sequences[split], tok),
                                                      device, batch_size, tok, precision)
        if metrics[split]['target_count'] != metrics[split+'_without_context']['target_count']:
            raise RuntimeError('context ablation changed evaluation targets')
    result = dict(format=CHECKPOINT_FORMAT, identity=identity, params=params, dataset=counts,
        epochs=history, best_epoch=best_epoch, evaluated_checkpoint='best.pt',
        evaluated_checkpoint_epoch=selected_identity['epoch'], optimizer_steps=steps,
        seen_target_tokens=sum(e['seen_target_tokens'] for e in history),
        seen_windows=sum(e['seen_windows'] for e in history),
        walltime_seconds=time.monotonic()-started,
        checkpoint_hashes={p.name: file_hash(p) for p in sorted(output.glob('*.pt'))}, **metrics)
    result['result_payload_sha256'] = canonical_hash(result)
    _write_json(output/'results.json', result)
    (output/'results.sha256').write_text(file_hash(output/'results.json')+'  results.json\n', encoding='ascii')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--initial-checkpoint', type=Path)
    for name, default in [('epochs', 6), ('batch-size', 24), ('max-tokens', 2048),
                          ('context-bars', 4), ('d-model', 256), ('num-layers', 6),
                          ('nhead', 8), ('dim-feedforward', 1024), ('seed', 20261029), ('checkpoint-every', 1)]:
        parser.add_argument('--'+name, type=int, default=default)
    for name, default in [('learning-rate', 3e-4), ('weight-decay', 0.01), ('dropout', 0.1),
                          ('progress-seconds', 60.0), ('checkpoint-seconds', 300.0)]:
        parser.add_argument('--'+name, type=float, default=default)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--precision', choices=('bf16', 'float32'))
    parser.add_argument('--usage-profile', default='research-noncommercial',
                        choices=('research-noncommercial', 'commercial-compatible'))
    args = vars(parser.parse_args(argv))
    result = train(**args)
    print(json.dumps(dict(best_epoch=result['best_epoch'], test=result['test'],
                          checkpoint_hashes=result['checkpoint_hashes']), indent=2))


if __name__ == '__main__':
    main()
