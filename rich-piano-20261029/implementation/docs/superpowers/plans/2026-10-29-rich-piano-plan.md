# Rich piano-only composition implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Actually train a texture-aware piano model and produce a more developed workday ballad with piano only.

**Architecture:** Frozen old model/outputs, additional audited real scores, new bar-conditioned/voice-aware codec and larger causal context, score-exact export and separately traced expressive piano rendering.

**Tech Stack:** Python/PyTorch, canonical score JSONL, MusicXML/MIDI, Verovio, native piano synthesis/FFmpeg, Orca Claude collaboration.

**Spec:** `docs/superpowers/specs/2026-10-29-rich-piano-design.md`.

## Global constraints

Piano only. No copied reference music. Existing user `experiment.log`, files and checkpoints preserved. Real scores distinguished from performance/synthetic data. Existing composer holdouts frozen. Research-NC profile retained. No UI or automatic data/weight publishing. Honest separation of authored controls and learned choices.

## Review focus

- Inferred outer-voice labels are weak geometry labels, not true hands.
- New scores from a held-out composer must not enter training.
- Control headers are input conditions, not easy targets counted as learned music.
- Dense/chordal notes must remain readable/playable, with the melody prominent.
- Pedal/performance rendering must not silently change the notated score.

## Tasks

- [x] 1. Claude: collect, convert and audit additional real solo-piano corpus; independently review design. Root validates counts and merges a leak-checked frozen split manifest.
- [x] 2. Root: failing codec/condition-mask/role/timing/split tests, then `src/omr/piano_rich/{__init__,tokenizer,train}.py` plus data-combination script. Preserve old module hashes.
- [x] 3. Run appropriate regression tests, stage exact code/data and launch real DGX training. Verify complete epoch coverage, selected checkpoint, evaluation and hashes.
- [x] 4. Generate richer one-piano arrangement with inner voice, varied accompaniment, voicing and section contrast; independently compare new and previous event features and XML/MIDI.
- [x] 5. Render score and expressive piano playback, inspect all PDFs, compare technical audio and music features, package scores/audio/training evidence and report actual outcomes.
- [x] 6. Validate Claude completion and review concerns, settle/release supervised workers, deliver concrete files and remaining limits.
