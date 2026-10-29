# Rich piano-only composition redesign

User scope: piano alone must sound harmonically and texturally rich, rather than single-note melody over the same four LH notes; collect actual scores and train a redesigned model with Claude collaboration. Preserve the user's workday story and original song as the comparison baseline. No additional instruments, no copied reference melody, no new UI. The YouTube URL was supplied as a qualitative target; automated access currently fails, so do not claim direct listening or transcribe it.

## Diagnosis and approved implementation direction

The last ballad has 221 notes, mostly a monophonic RH and repeated quarter-note LH arpeggios, no inner voice or sustained chordal bed, no explicit pedal performance, and a tiny general-MIDI soundfont. Technical XML/MIDI equality did not measure musical richness. Improve the score first, and render it with a piano sound bank and separate, traceable expression controls. The user explicitly requested redesign, collection and training; proceed within the existing research data profile.

## Model and data

- Separate namespace `omr.piano_rich`, new format and fresh checkpoint; preserve all previous `piano_music` code and weights so old samples remain reproducible.
- Continue exact 12tick/quarter canonical event data, simultaneous notes and full bars. Add per-bar observed texture/density/polyphony/harmony descriptors, and per-event outer-voice roles (bass/melody/inner) inferred from note geometry. These are reproducible weak descriptors, not human annotated hand or genre labels.
- Supply bar control headers as conditions, excluding them from training loss. Carry up to four preceding bars, max 2048 tokens. Train a fresh causal Transformer, width 256, six layers, eight heads, FF1024, dropout .1, bf16, AdamW 3e-4, seed 20261029, six full epochs. Adjust batch only if measured memory requires it; record actual values and coverage.
- Claude review adopted: use available true staff annotations for outer-role assignment with explicitly weak geometry fallback; do not infer hands solely from middle C. Exclude score-source velocity tokens from loss because score MIDI constants are not performer expression. Final voicing prominence/dynamics are documented performance controls.
- Claude continuation review adopted: per-note ATTACK new/held/unknown preserves known cross-bar tie continuation. Legacy rows without that source evidence remain unknown and are excluded from attack loss; never infer a fresh strike from a mere bar split. Concrete rearrangement currently authors fresh attacks plus separate damper-pedal interpretation.
- Ruling for concurrent collection: phase 1 performs three full epochs on the frozen base plus audited Sapp scores; phase 2 continues that exact same-format final checkpoint for three full epochs on the expanded corpus including vetted NIFC piano. Optimizer is intentionally reinitialized for phase 2 and all per-stage exposure/selection is reported. Continuation rejects a missing old source or changed split. This avoids idling GPU while the larger NIFC corpus is audited; it is not six exposures to every newly added NIFC score.
- Claude collects additional licensed REAL solo-piano score rows, source pins and hashes, rejects duplicates and withheld underlying-composition reviews. Root combines them with the final 1215-score manifest. Freeze existing composer split assignments; map additional rows of a known composer into the same split and allocate genuinely new composers deterministically. Detect exact/work/content leakage. Do not count redownloads, transpositions or synthetic examples as new scores.
- Distinguish raw candidates, accepted additional files, works, measures, notes, and actual train/validation/test exposure. Compare teacher-forced note-stage metrics only with explicitly matched populations; vocab-wide losses across formats are not comparable.

## Generation and notation

Use the new trained logits for actual note/voicing decisions, with explicit composition constraints for harmony and playability. Preserve original lyric sentences and melody identity as far as feasible. Add changing accompaniment: spacious intro, flowing verse, supported pre-chorus, chordal chorus, quieter outro; melody above inner voice; LH bass and broken-chord motion. Use inversions and controlled extensions as authored harmonic choices, not learned emotion semantics. Keep a true one-piano/two-staff score with independent voices, accurate rests/ties and explicit dynamics/pedal where supported. Provide score-exact MIDI plus a separately labelled expressive playback MIDI if timing/pedal differ. PDFs must match score notes; MP3 provenance must say which MIDI was rendered.

## Audio and acceptance

No strings/pads/drums to simulate fullness. A better piano bank, sustain, phrase dynamics and restrained room sound complement—not replace—the richer score. Use a publicly documented piano bank with retained attribution; technical clipping checks are not listening scores.

Acceptance includes: independent XML/MIDI equality, no hanging notes, complete lyrics, readable full-page PDF review, actual three-or-more-note sonorities and inner-voice presence with role separation, accompaniment diversity and section contrast compared with the previous score, data/split/coverage audit, actual GPU training logs and hashes, and new piano-only audio. Density/polyphony alone are diagnostics, not proof of quality. Preserve both old and new outputs and explain remaining limitations. No automatic GitHub upload of new data or weights.
