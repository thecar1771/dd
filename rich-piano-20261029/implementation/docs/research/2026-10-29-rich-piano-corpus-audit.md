# Rich solo-piano corpus addition and texture review (2026-10-29)

> Root integration addendum: the actual frozen GPU run uses 617 additions,
> not all 636 collector rows. `final-corpus-crosscheck.json` independently
> confirms every frozen addition is in the final 636-row set with exactly
> matching note/staff/tie content. Extra third-staff/ensemble exclusions and
> integration deduplication explain the unused rows. The full model manifest
> contains 1,832 files (train1,403 / validation199 / test230). Independent
> inline parser regression tests now exist in
> `tests/piano_rich/test_kern_parser.py` (12 cases); the complete suite passed
> 214 tests with 3 environment skips before subsequent performance work.

Corpus root: `artifacts/rich-piano-corpus-20261029/`. Collector: `scripts/collect_rich_piano.py`
(`fetch`, `candidates`, `rows`). Base for duplicate and split checks: the final 1,215-file manifest
`piano-only-20261028-final/data/pieces.jsonl.gz` plus its `policy-excludes.json`.

Everything collected is a **score encoding** (Humdrum `**kern`). There is no performance MIDI, no audio,
no transposed copy and no procedurally generated piece.

## Sources (pinned)

| Source key / corpus | Repository @ commit | License | Profile |
|---|---|---|---|
| `nifc` / `nifc_chopin_first_editions` | `pl-wnifc/humdrum-chopin-first-editions` @ `95dfb105c1669c72d10b04088566154f12d3dc1c` | CC BY 4.0 | commercial-compatible |
| `nifc` / `nifc_polish_scores` | `pl-wnifc/humdrum-polish-scores` @ `13ac964e0dd8bcd5fffd837169cbf653242c12e8` | CC BY 4.0 | commercial-compatible |
| `humdrum` / `sapp_joplin` | `craigsapp/joplin` @ `ad0840eb97e89fac7e89a94325a3d7526b0dc200` | CC BY-NC-SA 4.0 | research-noncommercial |
| `humdrum` / `sapp_haydn_sonatas` | `craigsapp/haydn-piano-sonatas` @ `299abc8f11eed4982f9fcddf2fc519b7b50b6214` | CC BY-NC-SA 4.0 | research-noncommercial |

- **Tarballs and hashes.** `audit/fetch.jsonl` has each codeload tarball URL, its sha256 and size, the
  number of extracted files and the `skipped_unsafe` list, which is empty for all four.
- **What was extracted.** Only `.krn` files and the top-level LICENSE/README files. Every member path was
  checked for safety before extraction.
- **Per-file hashes.** Every candidate's sha256 is in `candidates.jsonl`.
- **License evidence.** `audit/licenses.json` holds each repository's LICENSE text, its hash, the
  per-file `!!!YEM` license records and the latest composer death year among accepted rows.
- **Keeping the profiles apart.** NC and CC BY rows are written to separate files. Mixing them in one
  model makes the model research-noncommercial.

**Rejected sources, never downloaded as data:**

- `craigsapp/scriabin`, `craigsapp/hummel-preludes` and `craigsapp/chopin-preludes` have no license file.
- `craigsapp/beethoven-piano-sonatas` and `craigsapp/mozart-piano-sonatas` duplicate DCML works.
- `craigsapp/scarlatti-keyboard-sonatas` is harpsichord repertoire, excluded by the earlier policy.
- DCMLab `romantic_piano_corpus` is a subset of corpora already in the base.
- `choro` is lead sheets.

POP909 and other pop-piano MIDI sets were not used. They are arrangements of protected songs and are
not score ground truth.

## Counts

Totals: **9,502 candidate files → 636 accepted files**, i.e. 636 movements in 552 works by 70
composer groups, with 48,560 measures and 729,578 notes. Every accepted row is new relative to the
1,215-file manifest; duplicates are rejected, not counted. Row emission had 0 failures.

| Corpus | Candidates | Accepted files | Works | Composers | Measures | Notes | Profile |
|---|---|---|---|---|---|---|---|
| NIFC Chopin first editions | 512 | 22 | 15 | 1 | 2,160 | 36,171 | CC BY (base split: **validation**) |
| NIFC Polish scores | 8,918 | 573 | 503 | 67 | 42,158 | 638,077 | CC BY (new groups) |
| Sapp Haydn sonatas | 25 | 20 | 13 | 1 | 2,212 | 26,019 | NC (base split: train) |
| Sapp Joplin | 47 | 21 | 21 | 1 | 2,030 | 29,311 | NC (base split: train) |

**Exposure under the frozen split:** 22 rows in the validation group (Chopin), 41 rows in train groups
(Haydn, Joplin), and 573 rows in new groups for root to assign.

**Main rejection reasons:**

- **Chopin:**
  - 198 timing/tie ambiguity
  - 72 movements already in the base
  - 63 alternate editions
  - 136 not solo piano (songs 48, trio 44, cello 23, concertos and orchestra 20, two pianos 3)
  - 16 failed the conversion check (cadenza measures over 16 quarters, and similar)
  - 2 near-duplicates of base rows
- **Polish:**
  - 7,879 other instrumentation (choral, organ, voice and piano, undeclared)
  - 209 timing ambiguity
  - 102 withheld for an unknown death date
  - 66 texted keyboard scores
  - 36 with four or more staves, and 4 four-hands
  - 26 duplicate library copies
  - 9 failed the conversion check
  - 9 failed key normalization
  - 5 with a single staff
- **Haydn:** 3 ASAP duplicates and 2 timing.
- **Joplin:** 15 Mutopia duplicates and 11 timing.

**Largest accepted composers:** Stefani 65, Paderewski 53, Moszkowski 45, Łodwigowski 38, Śmietański 24,
Chopin 22, Wysocki 22, Mirecki 22, Joplin 21, Haydn 20, Szymanowska 18, Różycki 18, and others.

**Row files:**

- `rows/pieces-commercial-compatible.jsonl.gz`: 595 rows, sha256
  `669298682f4cc9d45e11a5a8aa5a0fa91dc79775eebe40fe5a00504cc97cfd2a`.
- `rows/pieces-research-noncommercial.jsonl.gz`: 41 rows, sha256
  `ae5773369f5c71ed2a52fe5ffedc26dabed065697f049d322b1a9766739bc4b9`.
- The raw tarball cache (111 MB) and the extracted `.krn` files (356 MB) stay under the corpus root.

## Acceptance rules (in order; every rejection is recorded in `candidates.jsonl:reject_reason`)

1. **Solo piano only.** Every `*I` instrument code must be `piano` or `forte`. Undeclared (`empty`)
   staves are rejected. Spines must be limited to `**kern`/`**dynam`/`**fing`; files with texted
   spines (songs printed as keyboard scores) are rejected. Files with a single keyboard staff, four
   hands, or four or more piano staves are rejected. Also rejected:
   - Chopin concertos and works with orchestra (opp. 2, 11, 13, 14, 21, 22).
   - Chamber works and their part files (opp. 3, 8, 65 and the Grand Duo).
   - The two-piano Rondo, op. 73.
   - The songs, op. 74.

   None of these are called solo piano.
2. **Rights in the underlying composition.** The composer's death year must be 1955 or earlier
   (life + 70). Files with an unknown death date, including `Anonim`, are withheld. Ids already
   withheld in the base `policy-excludes.json` stay excluded. Chopin's dates are not in the NIFC
   records, so the documented 1810–1849 is used. Every accepted composer died by 1953 (Różycki and
   Fitelberg died in 1953). This is not legal advice.
3. **Structural check with the independent reader.** The file must parse without error and have at
   least 4 measures and 32 notes. Every measure must fit the base codec's 1–192 ticks (16 quarters);
   cadenza measures are rejected rather than cut. The file must also pass the base
   `normalize_key`, so keyboard-range failures are handled the same way as in the base corpus.
4. **Conservative timing filter, requested by root after review.** Any file with an orphan tie
   continuation, an underfull voice measure, a spine merge with unequal voice time, a voice gap with
   no rest, mixed-duration chord tokens or pitchless spacer tokens is rejected.
5. **Editions and duplicates.**
   - **Chopin editions.** Chopin first editions are grouped by `chopin:op<N>#<no>`. One edition is
     kept per movement, chosen deterministically by edition code then path. The others are rejected as
     `alternate first edition` (versions, not new scores).
   - **Movements already in the base.** Rejected when the movement is already in the base: Chopin
     opus/number parsed from the ASAP, DCML and Mutopia titles; Haydn by Hob. XVI number and
     movement (ASAP); Joplin by title (Mutopia).
   - **Exact duplicates.** Rejected on unnormalized content, and on normalized `content_sha256`
     against the base.
   - **Near-duplicates.** Rejected when the top-line interval 6-gram Jaccard is 0.5 or more, against
     base rows of the same composer group and among new candidates of the same composer. This catches
     copies of one work held by different libraries.

## Row schema

The rows are in `rows/pieces-commercial-compatible.jsonl.gz` and
`rows/pieces-research-noncommercial.jsonl.gz`, one JSON object per line. Hashes are in
`rows/rows-summary.json`.

**Fields shared with the base `pieces.jsonl.gz`:**

- `id`, `source`, `composer`, `title`, `work_key`, `license`, `usage_profile`, `instrument`
- `mode`, `style`, `bars`, `key_normalization`, `conversion`, `content_sha256`, `newly_collected`

**Fields added:**

- `corpus`, `composer_dates`, `composer_key`
- `piano_music_group`: the base `composer_key()` grouping
- `frozen_split`: the base split of that group, or null for a new group
- `movement_key`, `attribution`, `url` (blob at the commit), `source_commit`, `source_sha256`
- `raw_path`, `score_type`, `role_policy`, `max_bar_tokens_v1`
- Chopin rows also carry `opus`, `number`, `edition` and `publisher`.

**Each bar** has the base `length`, `meter` and `notes` (`[onset, duration, pitch, 72]` at 12 ticks per
quarter), plus these per-note arrays in note order:

- `note_staff`: 1 is the top staff, from the `*staffN` spine labels.
- `note_voice`: the sub-spine index within the staff.
- `note_tie_from_previous_bar`: bool, true when the note continues a note held from the previous bar.
- `note_attack`: `new` or `held`.

**Conversion rules:**

- Ties are merged per staff and key in absolute time, then split again only at barlines, with the
  continuation flagged.
- Grace notes are counted, not modeled. Repeats stay in literal score order. Velocity is a constant 72.
- Off-grid endpoints (32nd notes and quintuplets) are rounded half-up to 12 ticks per quarter and
  counted in `conversion.quantized_note_fields`.
- Every bar was checked with `PianoTokenizer.encode_bar`.
- The role-preserving canonicalization is checked against `omr.real_music.data.canonical_notes`.

## Independent conversion check

`audit/scripts/crosscheck_rows.py` and `classify_mismatch.py` compare converted rows with the reader,
after undoing the key shift. They were run on root's first music21 batch
(`artifacts/rich-piano-first-batch-20261029`, 66 Joplin/Haydn files). Reports:
`audit/crosscheck-first-batch.json` and `audit/crosscheck-first-batch-classified.json`.

- **What agreed.** Bar-length sequences agree in all 66 files.
- **What did not.** Exact note multisets agree in only 19 files.
- **How the differences break down:**
  - **338 tie chains were not merged in the music21 rows.** Example: Antoinette m. 12, where the chord
    `[4.a [f# [d` → `4.a] f#] d]` comes out as two attacks.
  - **10 pitches were wrong.** Example: Haydn Hob. XVI:51/ii m. 28, where the source `[2.B` is B3 = 59
    and the rows have 57.
  - **A split-spine chord was misplaced.** Cleopha m. 10: the source `2ccc cc` is a pair of half notes;
    the rows give 6-tick notes a beat late.
  - **887 endpoints differ by one tick.** These are round-half-even versus half-up on 32nd-note half
    ticks, and are harmless.
  - **1,953 staff labels differ.** The rows used the initial clef; this audit uses the `*staffN` spine
    labels.
- **The batch also duplicated the base.** It contained 15 Joplin titles from Mutopia and 3 Haydn
  movements from ASAP.
- **Outcome.** Root quarantined that phase-1 run.
- **Bugs found in the reader itself.** The cross-check also exposed two of the reader's own bugs.
  Accidentals placed after other signs (`8BB^^-`, `16b]-`) were ignored, and a lone null line could
  advance time. Both were fixed before the final rows were produced.

## Texture diagnosis and design review

Diagnostics come from `audit/texture-stats-baseline.json` (`audit/scripts/texture_stats.py`). Hands are
split at MIDI 60, which is the rule the sample's notation used. These numbers describe texture; they
are not quality scores.

| | notes/bar | onsets with ≥3 notes | RH onsets with ≥2 notes | LH onsets with ≥2 notes | mean sounding at onset |
|---|---|---|---|---|---|
| previous ballad ("오늘도, 나의 자리") | 6.9 | 0.8% | **0.0%** | 0.9% | 1.86 |
| base training corpus (1,215 rows) | 15.2 | 23.5% | 34.7% | 28.1% | 2.93 |
| new rows, CC BY (595) | 15.2 | 36.1% | 45.0% | 39.0% | 3.30 |
| new rows, NC (41) | 13.0 | 27.7% | 39.5% | 31.7% | 2.95 |

The training data was rich. **The thin result was imposed at generation time, not learned.**

**Concrete causes:**

1. **`make_ballad.py` leaves the model almost no texture choices.**
   - The RH is one pitch per lyric slot (`pitches=[...]`, one `choose`), so it is monophonic by
     construction.
   - The LH is a fixed bass–5th–3rd–5th quarter-note pattern (half notes in quiet bars). It is
     authored, not sampled.
   - The model picks only the melody pitch, inside a ±5-semitone window and a register band, plus a
     velocity bin from a fixed range.
2. **`generate.PianoGrammar` caps texture further:**
   - at most 2 simultaneous notes per hand, within an octave
   - consonant dyads only, so no seconds, suspensions or added-tone inner voices
   - a 14-note bar cap, with `END_BAR` allowed after 5 notes
   - an eighth-note grid only and a fixed `LEN_48`
   - RH chord tones on beats 1 and 3 and scale tones elsewhere, with a 7-semitone RH step bound
   - hands assigned by MIDI 60
3. **The data representation hides structure:**
   - `dcml_bars` reads staff and voice and then drops them; MIDI sources merge tracks.
   - Notes held across barlines are split into new attacks with no flag.
   - Velocity is noise for score sources: a constant 72 for DCML, often 127 for Mutopia.
   - Within an onset, the melody (top) note is emitted last.
4. **The context is too short to learn phrasing.** Two context bars and 1,536 tokens cover about
   1–2 seconds of dense music. The only conditioning is mode/style, so phrase position, section and
   texture targets were not learnable.

**Recommendations (root's adopted design already covers many):**

1. **Multi-note RH voicings and an inner voice.**
   - Remove the per-hand caps.
   - Sample the number of notes per onset from logits. Bound only physical span (RH ≤ a 9th/10th,
     at most 4–5 notes per hand) and same-key overlap.
   - Allow seconds and suspensions in the inner voice; prefer resolving them, or let a voice-leading
     cost re-rank.
   - Use true staff from DCML and Humdrum rows for the roles. Geometry fallback is weaker and must be
     labelled.
   - In 3-staff rows, staff 2 is a middle staff: map staff ≥ 2 to the LH or use geometry.
2. **Melody prominence.**
   - Within an onset, emit `ROLE_melody` first, or order notes top-down, so inner notes are
     conditioned on the melody.
   - At generation, require exactly one melody note per RH onset that has the melody, with the melody
     as the top RH note, inner voices at least a minor third below, and no crossing.
   - Prominence in audio belongs to the separately labelled expressive MIDI (melody +10–15 velocity).
     Do not learn it from score velocities, which root now masks.
3. **LH variation.**
   - Condition each bar on texture/density/polyphony controls and let the model choose the pattern:
     waltz bass–chord–chord, broken 8ths spanning a 10th, sustained bass with afterbeats, stride, and
     so on.
   - Use `ATTACK_held` for pedal-point basses.
   - Reject a sampled LH bar identical to either of the previous two unless the plan marks a reprise.
   - The new rows add a lot of LH dance and lyric figuration, largely Polish salon waltzes, mazurkas,
     polonaises and nocturnes.
4. **Harmonic voice leading and phrase contrast.**
   - Keep harmony and form honestly authored, but pass inversions, 7ths and sus chords as
     conditions.
   - Re-rank several model samples per bar by model log-likelihood plus a voice-leading penalty
     (total inner-voice movement, parallel 5ths/8ves in the outer voices).
   - Give each section different controls (intro sparse/layered, verse flowing/broken, chorus
     dense/full).
   - The claim that is defensible is that the model learned to realize the requested texture. It did
     not learn the song form.
5. **Training on descriptors and larger context.**
   - The four-bar / 2,048-token context and controls excluded from loss are right.
   - Make sure every target bar gets context bars, including bars at a window's start.
   - Controls describe the target bar, so they make teacher-forced loss easier. Compare losses only
     with matched baselines.
   - Measure control adherence on held-out prompts: does the generated bar's descriptor equal the
     requested one?
   - Report per-role note-stage loss.
   - Sample with composer weighting so Moszkowski, Stefani and Paderewski do not dominate the new
     training exposure.

## Split and leakage notes

- **No leakage was checked beyond what is listed here.** Duplicates were checked against the base by
  movement key, exact content and same-group near-duplicates.
- **Base composer groups stay frozen.** The base group `chopin` is entirely **validation**, so every
  accepted Chopin row adds validation data only and no training exposure. `haydn` and `joplin` are
  train.
- **New Polish composer groups** have `frozen_split = null`. Root assigns them by deterministic 80/10/10
  hashing.
- **Surnames are grouped conservatively.** Scharwenka (Xaver, Philipp), Kątski, Stefani, Wieniawski,
  Jarecki and Krogulski each share one group.

## Reproduce

```
python -I scripts/collect_rich_piano.py fetch      artifacts/rich-piano-corpus-20261029
python -I scripts/collect_rich_piano.py candidates artifacts/rich-piano-corpus-20261029 <final>/data/pieces.jsonl.gz <final>/data/policy-excludes.json
python -I scripts/collect_rich_piano.py rows       artifacts/rich-piano-corpus-20261029 <final>/data/pieces.jsonl.gz
python -I artifacts/rich-piano-corpus-20261029/audit/scripts/license_evidence.py artifacts/rich-piano-corpus-20261029
```

## Not done / limits

- **The reader is new code.** It agrees with the source on every case checked by hand: ties,
  accidentals, split spines, tuplets and pickups. It has no unit-test file, because tests were outside
  this worker's ownership.
- **Score-level limits:**
  - Rounding to 12 ticks per quarter blurs 32nd notes and quintuplets.
  - Pedal, grace notes, ornaments and dynamics are not modeled.
  - Velocity is constant.
- **Excluded for rights:** Polish files with unknown death dates (including `Anonim`) are withheld, not
  cleared.
- **Not collected:** KernScores material without an explicit license, MAESTRO and other performance
  MIDI.

## Relation to the launched training run

Root froze an earlier **v1** emission of these rows (882 rows) in its own immutable snapshot,
`artifacts/piano-richness-20261029/input-snapshot-v1`, and applied its own strict filters:

- the six timing flags
- staff outside 1/2
- Chopin op. 73 and the "Secondo" file
- empty or unknown composers

That left **617 new rows (579 NIFC + 38 Sapp)** in the final manifest (sha256
`a6b9f6959d…c73c1`; 1,832 files in all, split train 1,403 / validation 199 / test 230). The training
counts come from root's frozen manifest.

The `rows/` files in this corpus root are the later **v2** emission (636 rows) with the same rules
built in. In v2:

- 38 Chopin files that the composer-name bug had withheld were recovered.
- The two-piano Op. 73 file is excluded.
- 3-staff files are kept, so staff 3 can occur.

v2 was **not** used for the launched run.
