# Old score-v3 G0 diagnostic

The bounded diagnostic completed on 2026-10-28 KST; **full generation G0 did not pass**. This examines old weights only and is independent of the new finite genre codec. No training, weight repair, dependency installation, GPU use, or old-artifact writes occurred.

## Observed generation

Both seeds sampled 128 new tokens and reached the token cap without EOS. Sampling used the complete 838-token vocabulary, temperature 1, no top-k or grammar filtering, `eval()` and `torch.inference_mode()` on CPU. The 18-token prefix contains `BOS SCORE_V3` and genuine minimal part headers emitted by the old codec: p1/voice/one staff and p2/piano/two staves. It contains no measures or gold note continuations.

| Seed | EOS | Native decoder | Events | Additional structural validation |
| --- | --- | --- | --- | --- |
| 20261028 | No | `ValueError: invalid literal for int() with base 10: 'MEASURE_NUMBER'` | Unknown because decoding failed | `unexpected top-level token '321' at 18` |
| 20261029 | No | Returned a record | 5 | `unexpected token 'FAMILY' at 22` |

Indices in errors are zero-based indices in the full prefix-plus-generated stream. The first continuation begins `321 INSTRUMENT piano 12 PART_BARLINE p1 MEASURE_NUMBER 1 ...`; the second begins `QF_STEP_Q_0_1 MEASURE PART_ID p1 FAMILY QF_DURATION_Q_2_1 QF_PITCH_Q_71_1 ...`. Full token IDs, tokens, excerpts and exact errors are in the JSON evidence.

The existing `decode_score_v3` can skip unknown fields and consume malformed groups. Its second returned record is **not** evidence of a valid five-event score: the script separately rejects the unexpected measure field and records missing termination. The script checks known plain-v3 structure and timing in addition to calling the native decoder; it is not a musical-quality evaluator. There was no complete score, export, listening assessment, or token-list roundtrip quality claim. These two bounded samples do not establish that every possible sampling configuration must fail.

All 37 and 42 generated fused rational tokens respectively were decoded through the old `read_numeric` API into exact `Fraction` values and checked against the supplied train-fitted rational table. For example `QF_STEP_Q_1_3` becomes exactly `1/3`; `QF_DURATION_Q_1_8` becomes `1/8`. Malformed structure is therefore distinguished from unsupported compact-number decoding.

## Identity and evidence

Remote host: SSH alias `sparkey17`. Old root: `/home/sparkey17/score-tokenizer-v2-run`. New output directory: `/home/sparkey17/genre-g0-20261028`.

- Final remote evidence: `diagnostic-final.json`; local copy: diagnostic-final.json（로컬 보관 경로: `../../artifacts/genre-g0/diagnostic-final.json`）.
- Final evidence SHA-256: `94a5101349f66a489d06c3bcfde8cb91d957a1953ca8665ec8643b8aada12464`.
- Checkpoint: `artifacts/score-pretraining-v3-grouped/score-transformer-v3-grouped-v1-final.pt`, SHA-256 `8b314ed0055b9dfeefbfcbd90846c71f88bb47bee6fa86e7f7f65d5f7bc5e5a9`.
- Vocabulary file SHA-256: `beb048d00925f5c907f9d76e4efc0c8955d24f0434827498b3d2b65ebc286d24`; canonical token-list hash: `9b0d32fd925571ac26553ba678160406884bb77ecb0a148a0a368488ce7c5b24`.
- Rational-table file SHA-256: `461a471e5b17ad44c90f8371a067c7d3af19a19cd3ef4d601ce1362cb1419a63`; canonical table hash: `e7f734991c9c0830b6c4f638cabaa5d3f542c4fca6f8605e6ae52673e7d35423`.

The script uses `torch.load(..., map_location='cpu', weights_only=True)` with no unsafe fallback, verifies checkpoint/sidecar token lists, format, numeric encoding, table contents and canonical hashes, checks model dimensions, and strictly loads `model_state`. Configuration: d_model=128, four heads, four layers, feedforward=512, max context=512, dropout=0.1 (disabled for inference). Existing checkpoint metadata says final-step, training step 1352, training seed 20261025. Config hash and hashes of the old model, codec and parser source files are in the JSON.

Runtime: Python 3.12.3, PyTorch `2.10.0a0+b558c986e8.nv25.11`, two CPU threads. Cached image `nvcr.io/nvidia/pytorch:25.11-py3`, image ID `sha256:eea3fe49e8a583008e4ea66fbeb36b2a7a111db8e1e322d2f310fd697baad95b`. JSON timestamps use the remote clock. Container root, old source/checkpoint/data mount and diagnostic script mount were read-only; only the new output mount and temporary in-memory `/tmp` were writable. Networking and GPU visibility were disabled.

## Reproduce

Use the final script（로컬 보관 경로: `../../scripts/genre_g0.py`） with the existing old source tree; this local genre-bootstrap tree does not contain the old model API. There is no generation method in the old model class, so the script implements bounded next-token sampling through `MultiPartScoreTransformer.forward`. The code does not import the old trainer or mutate any model state.

The actual final remote invocation was the following (the script was staged as `genre_g0-final.py`). For a replay, select a new nonexistent output JSON/log name; the diagnostic refuses an existing output file.

```sh
docker run --rm --user 1000:1000 --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=128m \
  --network none --cap-drop ALL --security-opt no-new-privileges \
  --cpus 2 --memory 4g \
  -e PYTHONDONTWRITEBYTECODE=1 -e CUDA_VISIBLE_DEVICES= \
  -v /home/sparkey17/score-tokenizer-v2-run:/old:ro \
  -v /home/sparkey17/genre-g0-20261028/genre_g0-final.py:/diagnostic.py:ro \
  -v /home/sparkey17/genre-g0-20261028:/output:rw \
  nvcr.io/nvidia/pytorch:25.11-py3 python /diagnostic.py \
  --source-root /old \
  --checkpoint /old/artifacts/score-pretraining-v3-grouped/score-transformer-v3-grouped-v1-final.pt \
  --vocabulary /old/artifacts/score-pretraining-v3-grouped/score-vocabulary-v3-grouped-v1.json \
  --rational-table /old/artifacts/score-pretraining-v3-grouped/rational-token-table.json \
  --output /output/diagnostic-final.json --seeds 20261028 20261029 --max-new-tokens 128
```

Initial setup exposed a read-only-container temporary-directory requirement, addressed with `/tmp` tmpfs. The first staged diagnostic completed inference but failed to write its JSON under the image's default user; the preserved `run-initial-permission-error.log` records that failure. Running as the directory owner (1000:1000) wrote `diagnostic.json`; a final script revision added independent compact-rational checks and more precise structural errors and wrote `diagnostic-final.json`, preserving all earlier remote files. Both successful runs produced identical generated token IDs for each fixed seed. The result is scoped to this CPU environment; byte-identical reports are not expected because timestamps and elapsed time vary.

## Verification and decision

The actual final remote run wrote the JSON and printed its matching SHA-256 in run-final.log（로컬 보관 경로: `../../artifacts/genre-g0/run-final.log`）. Local verification parsed the script AST, checked the local script hash against the executed remote script hash, compared both runs' generated IDs, and checked the final JSON hash. A missing-checkpoint CLI invocation exited 2 before importing torch and created no output. See verification.json（로컬 보관 경로: `../../artifacts/genre-g0/verification.json`） for the exact negative command and captured error. No broad tests were run for this isolated diagnostic.

Ruling: collecting exact malformed-output evidence fulfills the approved bounded G0 diagnostic task; it does not satisfy the original full vocal/piano generation gate. `full_generation_g0_pass` is deliberately false. The new genre codec/training work can proceed independently, without treating old teacher-forced scores or permissive decoder returns as generation success.
