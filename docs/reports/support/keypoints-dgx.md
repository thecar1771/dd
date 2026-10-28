# DGX Spark masked keypoint experiment — 2026-10-24

## Outcome

PASS. The full test suite, CUDA training, safe checkpoint reload, description
demo, SmolVLM photo caption, interpretation, and MusicXML export completed on
the DGX Spark. This is a pipeline smoke test, not a quality claim: the training
corpus is deterministic project-authored template data, and the learned outputs
remain visibly underfit.

## Reproducibility record

- Source commit: `e473b60` (`feature/omr-training-poc`)
- Source archive SHA-256: `dc7d5bce5b6a8ed0d04777e681d2b15b8168368dd6243fbd6e274741f3ae1788`
- Host: `spark-de75.tail51f2fa.ts.net`
- Final verification time: `2026-10-24T14:59:23+09:00`
- GPU: NVIDIA GB10
- Driver: `580.126.09`
- Container: `nvcr.io/nvidia/pytorch:25.11-py3`
- Container image ID: `sha256:eea3fe49e8a583008e4ea66fbeb36b2a7a111db8e1e322d2f310fd697baad95b`
- PyTorch: `2.10.0a0+b558c986e8.nv25.11`
- Vision smoke versions: Transformers `5.20.2`, Accelerate `1.15.0`,
  Hugging Face Hub `2.3.0`, Pillow `12.0.0`
- Seed: `1701`
- Samples: 2,000 generated `CC0-1.0` records covering `ko`, `en`, `ja`,
  `es`, and `fr`
- Generated corpus SHA-256:
  `1cde9a033b5ab9622485b14a24a5504f5a753e2d27e2266ad728fa82f3a51dbf`
- Model: maximum 160 bytes, width 128, 8 attention heads, 2 layers,
  feed-forward width 256, dropout 0.1, consistency weight 0.25
- Optimizer: AdamW, learning rate `0.001`
- Steps: 200; batch size: 64; unique samples seen: 2,000
- Training runtime: `3.972201250027865` seconds
- Initial total loss: `4.5594892501831055`
- Final losses: total `2.7278711795806885`, keywords
  `0.3668513894081116`, emotion `0.1679946780204773`, masked concept
  `2.1279213428497314`, consistency `0.2600414719581604`
- DGX suite: 55 passed in 1.39 seconds
- Local suite: 54 passed, 1 POSIX-only launcher test skipped on Windows

## Artifacts

The final clean run directory was
`/home/sparkey17/OMR/omr-keypoint-poc-e473b60`. The launcher runs the
container as the calling UID/GID, so every bind-mounted artifact is owned by
`sparkey17:sparkey17` rather than root.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `keypoint-mask.pt` | 3,916,675 | `1507b30d4c5738e2e224c37413421df7b0757dc87f2525d254cf16de98c0473d` |
| `warm-forest.musicxml` | 1,875 | `5e62d4859b0c300cb1ed8666156b07b87b67f16fe4b6240eba0a134961b56107` |
| `warm-forest.interpretation.json` | 432 | `191ed01933da87aba5f39fa757f243e860e15346059a7a6025bc010d43c4251f` |
| `bee.jpg` | 5,373,297 | `8b21ba78250f852ca5990063866b1ace6432521d0251bde7f8de783b22c99a6d` |
| `bee.musicxml` | 1,850 | `e8de982fed077e4aeaaddb0f5ec5ded8b011f23b4acd08e3da89921dd43ec856c` |
| `bee.interpretation.json` | 503 | `8bcda26c95dcdcd9305085f10407e615ebb74137535efe3559efca3df5c442264` |

Both MusicXML files parsed successfully with Python's
`xml.etree.ElementTree`.

## Commands

The training and description smoke test used:

```bash
cd ~/OMR/omr-keypoint-poc-e473b60
bash scripts/dgx_keypoint_train.sh
```

The real-image path used the public example image from the official Hugging
Face image-to-text documentation. The image was used only for inference and was
not added to the training corpus or repository:

```bash
curl --fail --location \
  https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/bee.jpg \
  --output artifacts/dgx-keypoints/bee.jpg

docker run --rm --gpus all \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  --workdir /workspace \
  --env HOME=/tmp \
  --env PYTHONPATH=/workspace/src \
  nvcr.io/nvidia/pytorch:25.11-py3 \
  bash -lc '
    python -m pip install --quiet --user \
      "transformers>=4.49,<6" "accelerate>=1.0"
    python -m omr.pipeline artifacts/dgx-keypoints/keypoint-mask.pt \
      --image artifacts/dgx-keypoints/bee.jpg \
      --language ko \
      --user-hint "벌과 꽃의 생명력을 유지해줘" \
      --output artifacts/dgx-keypoints/bee.musicxml
  '
```

SmolVLM captioned the photograph as flowers and plants. The downstream smoke
model selected `sunlight`, `person`, and `forest`, with `cold_solitude` as the
primary emotion. The user hint remained a separate field and did not override
the model-selected emotion.

## Debugging record

The first DGX launcher created bind-mounted artifacts as root. A regression test
executed the launcher against a fake Docker boundary and failed because the
`--user` argument was absent. Commit `e473b60` added the calling UID/GID and a
writable temporary home; the regression test then passed on Linux, and a clean
CUDA run confirmed all generated files were owned by `sparkey17`.

An exploratory photo command using `pip --target` installed a second,
incompatible PyTorch and failed while importing `torchvision::nms`. Retesting
with `pip --user` preserved NVIDIA PyTorch and completed successfully. The
container's preinstalled `datasets 4.4.1` still reports a resolver warning
against Hugging Face Hub 2.3.0; that package is not used by this inference path.

## Limitations and next gate

- The corpus proves multilingual masking mechanics, not open-vocabulary scene
  understanding or generalization to real captions.
- The masked-concept loss remains the largest objective component, and both
  demo interpretations contain semantically weak predictions.
- The photo adapter downloads model weights on first use and currently relies
  on bounded rather than lockfile-pinned optional dependencies.
- CUDA is seeded, but the run is not guaranteed bitwise deterministic.

Before quality evaluation, add a license-reviewed real-caption validation set,
freeze the vision dependency lock, and report per-concept and per-emotion
metrics on held-out photographs. Do not treat this smoke checkpoint as a
production or musical-quality baseline.

## Post-review verification

Five whole-branch review findings were fixed in commit `9b660ad`: strict
tokenizer/checkpoint metadata compatibility, fractional MusicXML timing and
start placement, rejection of unsupported meter encodings, UTF-8-safe caption
fitting to the model context, and non-root execution for both DGX launchers.

- Source archive SHA-256:
  `737418505f691f109ecf88e05b3858aa101d32ef6de8124c6fe4153c9a3f4ef2`
- Clean DGX directory: `/home/sparkey17/OMR/omr-keypoint-poc-9b660ad`
- Verification time: `2026-10-24T15:26:03+09:00`
- Keypoint launcher: 61 tests passed, CUDA training and description-to-MusicXML
  demo passed.
- Melody launcher: 61 tests passed, CUDA training and safe checkpoint reload
  passed with finite logits.
- Both artifact trees were owned by `sparkey17:sparkey17`.
- The generated `warm-forest.musicxml` parsed successfully after the timing
  preservation change.
