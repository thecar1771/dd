# Rich piano model and sample commands

This path uses only acoustic-piano score material. It preserves the previous
`omr.piano_music` model implementation and adds `omr.piano_rich` separately.

The completed run artifacts are written outside source control at:
`C:/Users/theca/orca/projects/OMR/artifacts/piano-richness-20261029/final/`.
Use its training report, dataset summary and SHA256 manifest as the authority for
actual completed training and selected weights. A launch command alone is not
completion evidence.

## Train

With `src` on `PYTHONPATH`, PyTorch and the project dependencies available:

The optional performance/verification scripts also require `mido`
(`python -m pip install mido`). PDF engraving uses the existing Verovio/Edge
workflow separately from model training.

```text
python -m omr.piano_rich.train --manifest <pieces.jsonl> --output <empty-run-dir> --epochs 6 --batch-size 24 --max-tokens 2048 --context-bars 4 --d-model 256 --num-layers 6 --nhead 8 --dim-feedforward 1024 --seed 20261029 --device cuda --precision bf16 --usage-profile research-noncommercial
```

The final run initializes fresh. The earlier three-epoch music21 experiment is
quarantined because independent source comparisons found conversion errors. Its
weights must not be used as final weights or as an initial checkpoint.

## Produce the workday ballad arrangement

```text
python scripts/generate_rich_piano_ballad.py --checkpoint <best.pt> --baseline <ballad-workday-sample-dir> --output <empty-new-sample-dir> --device cuda
python scripts/verify_rich_piano_sample.py --sample <new-sample-dir> --baseline <ballad-workday-sample-dir>
python scripts/make_piano_performance.py --midi <new-sample-dir>/piano/score.mid --output <new-sample-dir>/performance.mid
```

The lead pitches and rhythm are preserved for a controlled comparison. The new
model chooses accompaniment and inner-note pitches among playable harmonic
candidates. Section rhythms, harmony candidates, hand ranges, velocities and
performance controls are authored. The model is not an end-to-end image-to-song,
emotion classifier, singing model or learned human-performance renderer.

`score.mid` is score-exact. `performance.mid` is separately labelled playback
with tiny timing/velocity changes and CC64 pedal. The PDF/MusicXML contain one
piano part with two staves; the lyric and piano-only editions have the same
notes. Original private image contents are not packaged.

## Data provenance

`scripts/collect_rich_piano.py` fetches pinned, licensed sources and emits the
audited score rows. See the corpus audit report for the exact pins and policy.
The actual model uses 617 additions, independently checked as an unchanged
subset of Claude's final 636-file collector output. The extra exclusion of
third-staff identities and ensemble ambiguities is intentional. The complete
integration, rejection and input-hash evidence is in the artifact bundle.

Score-derived velocity constants are masked from loss. Unknown legacy attack
labels are also masked. Score staff/voice labels are retained when present;
weak geometry is used for legacy rows without staff evidence. Neither supplies
ground-truth fingering or expressive performance supervision.
