# Solo-piano score corpus audit (2026-10-28)

Corpus root: `artifacts/piano-score-corpus-20261028/`. Manifest: `source-items.jsonl`
(sha256 `3ba458847e0dc9a1e1a0779ea64f3f946bc222c6ff1abdde20d7ace543634e61`).

**Usage profile: `research-noncommercial` only.** Every row is CC-BY-NC-SA-4.0. None of it is
commercial-compatible, so keep it out of the earlier commercial-compatible models and their data.
Any derived data or model must carry the attribution and ShareAlike terms.

## What was collected

Everything here is a score encoding: no performance MIDI, no audio, no transposed copies.

| Source | Repo @ commit | Score items | Works |
|---|---|---|---|
| ASAP | `fosfrancesco/asap-dataset` @ `afc815c75c42e83a79c03feb6da8a35e77d4c6b8` | 221 (`midi_score.mid` + `xml_score.musicxml` + beat/downbeat/time-sig annotations) | — |
| DCML | 23 repos pinned by `DCMLab/distant_listening_corpus` @ `12be0d3ff7c6e0ef67c7d4e8e44541e5f288f39d` + 8 standalone `debussy_*` repos (HEAD of `main`) | 656 (`notes` + `measures` TSV + `.mscx`) | — |
| **Total** | | **877 distinct score files; 816 after cross-source dedupe** | **252 works** |

Content totals: 1,648,949 notes (1,440,628 after dedupe). DCML adds 66,528 measures and 58,094
tied-note rows; the raw `tied` column is kept (1 = start, 0 = continue, −1 = end).

Commits for each repo, tarball URLs, tarball sha256 and extracted file counts are in
`audit/fetch_asap.json`, `audit/fetch_dcml.jsonl` and `audit/fetch_dcml_debussy.jsonl`.
The license evidence for each repo is in `audit/licenses.json`: LICENSE, README, CITATION.cff and
.zenodo.json. In every DCML repo the README and .zenodo.json say NC-SA, while some CITATION.cff
files say CC-BY-NC-4.0. The stricter NC-SA is applied.

Items by composer: J.S. Bach 148, Beethoven 148, Chopin 90, Debussy 84, Grieg 66, Mozart 60,
Koželuch 49, Liszt 35, J.C. Bach 29, Rachmaninoff 26, Schumann 22, Medtner 19, Bartók 14,
Schubert 13, Dvořák 12, Tchaikovsky 12, Haydn 11, Ravel 9, W.F. Bach 9, Händel 6, Schulhoff 6,
Poulenc 3, Scriabin 2, and 1 each for Balakirev, Brahms, Glinka and Prokofiev. Per-corpus and
works-per-composer counts are in `audit/summary.json`.

## Exclusions (`audit/excludes.jsonl`, 178 rows)

- **144 harpsichord-encoded pieces.** These are keyboard music without piano: `scarlatti_sonatas`
  69, `cpe_bach_keyboard` 66 and `couperin_clavecin` 9. Their raw files stay on disk but are not in
  the manifest.
- **14 ASAP repeat-structure variants** (`*_no_repeat`, `*_repeat`, …) where the base score is
  kept. ASAP folders that exist only as a variant are kept, e.g. `Chopin/Sonata_2/1st_no_repeat`.
- **20 DCML corpora never downloaded:**
  - string quartets and chamber music: ABC, Mendelssohn, Pleyel, Corelli, couperin_concerts
  - solo strings and flute: bach_solo
  - organ: Frescobaldi, Sweelinck
  - orchestral piano reductions: Wagner overtures
  - voice or voice + piano: lieder, Winterreise, Kindertotenlieder, Stabat Mater, Euridice,
    madrigals, Schütz, chorales
  - superseded legacy duplicates: `debussy`, `debussy_piano`
- **No four-hand or two-piano music is present.** All 877 rows are solo piano: 628 use 2 staves,
  26 use 3 and 2 use 4 (Rachmaninoff op. 42).
- **Notes on the kept rows:**
  - `bach_en_fr_suites` and `handel_keyboard` are encoded with Piano staves, so they were kept.
    They are historically harpsichord repertoire; drop corpora by `corpus` if needed.
  - The staff labels for Grieg (`Midi_1`) and Mozart (`Klavier linke Hand`) are cosmetic. These are
    piano scores.
- **No fetch errors and no unsafe archive members.** Extraction only accepts regular files whose
  normalized paths stay inside the destination; the `skipped_unsafe` list is empty for every repo.

## Rights in the underlying compositions

The CC license covers DCML's encoding. It does not clear the composition itself. 31 rows carry a
`composition_rights_flag`:

- **Poulenc, *Mouvements perpétuels* (3 rows).** Poulenc died in 1963, so under life+70 the work is
  protected until 2034. It is **not cleared**, so exclude it.
- **Schulhoff, *Suite dansante en jazz* (6 rows).** Schulhoff died in 1942, so the work is public
  domain under life+70. It was published in 1931, so US protection may last to the end of 2026.
- **Rachmaninoff, op. 42 (22 rows).** Rachmaninoff died in 1943, so the work is public domain
  under life+70. It was published in 1931, so US protection may last to the end of 2026.

Every other composer died before 1956 and the works are older than these.
This is not legal advice.

## Dedupe and split guidance

- `work_key` (e.g. `beethoven:piano-sonata-01`, `mozart:k310`, `grieg:op12`, `bach:bwv846`)
  groups movements and versions of one composition. It uses a composer prefix, so opus numbers are
  never compared across composers.
- `movement_key` = `work_key#movement`. Rows that share a `movement_key` across sources have
  `dedupe_preferred=false` on the ASAP copy, plus `duplicate_of`.
- The 61 duplicates are 49 Beethoven sonata movements, 5 Mozart, 2 Debussy, 1 Liszt and 2 Ravel.
  DCML is preferred because it has explicit measures and ties. ASAP `9-2_no_trio` and `31-3_4` are
  grouped with the full DCML movements.
- Split train and eval by `work_key`, not by row.
- **Overlap with the existing Mutopia data.** `audit/mutopia-overlap.jsonl` is a heuristic
  composer + catalog-number match against the 581 Mutopia solo-piano entries. It found 118 items
  across 39 works that may also be in Mutopia: WTC preludes and fugues, several Beethoven sonatas,
  Chopin op. 10 and op. 25, K331, K545, and others. Treat these as leakage candidates when Mutopia
  data and this corpus are both in a split.

## Manifest schema (one JSON object per line)

- **Fields on every row:** `id`, `source` (`asap`|`dcml`), `corpus`, `composer`, `composer_key`,
  `title`, `work_title`, `movement`, `work_key`, `movement_key`, `dedupe_group`,
  `dedupe_preferred`, `duplicate_of?`, `instrument` (`piano`), `license`, `usage_profile`, `url`,
  `source_commit`, `sha256{...}`, `n_notes`, `time_signatures`.
- **ASAP rows add:**
  - `midi_path` (`raw/asap/<folder>/midi_score.mid`), `score_path` (MusicXML), `beats_path`
  - `midi_tracks`, `ticks_per_beat`, `n_time_signature_events`, `key_signatures`,
    `n_downbeats_annotated`
- **DCML rows add:**
  - `notes_path`, `measures_path`, `score_path` (MS3 `.mscx`), `work_number`
  - `staff_instruments`, `n_measures`, `n_staves`, `n_tied_notes`, `tied_value_counts`,
    `has_repeats`, `has_voltas`, `notes_columns`
  - Eight standalone Debussy repos use `notes/<piece>.tsv` (not `.notes.tsv`). The columns are
    the same.

All paths are relative to the corpus root and were checked to exist. The sha256 of each referenced
file is in `audit/file-hashes.tsv` (2,631 files), and the hash of every extracted raw file is in
`audit/raw-file-hashes.tsv` (3,242 files, 746 MB).

## Reproduce

Run the scripts in `audit/scripts/` with `python -I`:

1. `fetch.py owner repo sha dest kind cache` downloads the codeload tarball at a pinned commit and
   extracts only the allowlisted score files.
2. `build.py <corpus_root>` writes the manifest and the audit sidecars.
3. `mutopia_overlap.py <corpus_root> <mutopia_classified.jsonl>` writes the Mutopia overlap check.

## Not done

- MAESTRO performance MIDI was not collected. It is optional and would not be score data.
- Aria and audio were not touched.
- Further DCML-format sources outside DCMLab were not collected.
