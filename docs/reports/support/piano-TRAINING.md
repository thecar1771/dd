# 실제 피아노 재학습 재현

이 모델은 1,215개 실제 피아노 악보를 정리한 자료 중 학습용 866개 파일을 6회 모두 순회했습니다. 검증 130개와 최종 평가 219개 파일은 가중치 학습에서 제외했습니다.

원본 이미지 인식이나 오디오 생성 학습이 아니라, 실제 악보의 피아노 양손 음표를 함께 예측하는 기호 음악 모델입니다. 추가 자료의 조건을 따라 비상업적 연구용으로 관리합니다.

## 원자료와 변환

`data/pieces.jsonl.gz`의 압축 해제 후 SHA256은 다음과 같습니다.

```text
4f78ac0a3ad5aae7bde02054edac86a67d2f01f83dd8f98948d0b3899965fb5a
```

1,215개 파일은 584개 작품 그룹, 114,066마디, 1,736,760개 정리된 음표입니다. 새로 확보해 수용한 파일은 912개입니다. 파일·악장·작품 그룹과 반복 학습 횟수는 구분합니다.

원자료 수집·변환 재현 코드는 `code/scripts/prepare_piano_scores.py`, `finalize_piano_data.py`, `repair_piano_midi.py` 및 `audit/scripts/`에 있습니다. 학습에 쓰인 정확한 변환 결과는 위 압축 manifest입니다. MIDI는 양손을 절대 시간축에서 먼저 합친 뒤 재타격을 정리하고, 모든 빈 마디의 박자표를 보존해 분할합니다.

## 학습 명령

실제 실행 환경은 NVIDIA GB10, `nvcr.io/nvidia/pytorch:25.11-py3`, Python 3.12.3, PyTorch 2.10.0a0+b558c986e8.nv25.11, CUDA 13.0입니다. 해당 환경에서 3,383,296개 파라미터를 새로 초기화했습니다.

Linux CUDA 환경에서 압축을 풀고 새 출력 폴더로 실행합니다.

```bash
gzip -dk data/pieces.jsonl.gz
export PYTHONPATH=code/src
export CUBLAS_WORKSPACE_CONFIG=:4096:8
python -m omr.piano_music.train --manifest data/pieces.jsonl --output runs/new-piano-run --epochs 6 --batch-size 24 --max-tokens 1536 --context-bars 2 --d-model 256 --num-layers 4 --nhead 4 --dim-feedforward 768 --seed 20261028 --device cuda --precision bf16 --usage-profile research-noncommercial
```

실제 실행된 `code/scripts/dgx_piano_train.sh`는 DGX 디렉터리 배치용입니다. 묶음에서 직접 재학습할 때는 위 명령의 경로를 사용합니다. 실행 하드웨어와 라이브러리가 다르면 같은 seed만으로 동일 바이트의 가중치를 보장하지 않습니다.

## 결과와 해석

- 6 epoch, 1,164 optimizer step, 34,226,616개 목표 토큰 제시
- 매 epoch 4,637개 학습 window, 5,704,436개 목표 토큰을 빠짐없이 사용
- 가장 좋은 검증 epoch 6의 `best.pt`로 최종 평가 및 두 독주 예제 생성
- 최종 평가 손실 1.225677 / 문맥 제거 후 같은 목표의 손실 1.407192
- 전체 다음 토큰 정확도 61.1507%, 음높이 토큰 정확도 8.2890%
- 기록된 학습·평가 시간 389.82초
- 최종 체크포인트 SHA256: `3ac0e307969432afffe3e7acf6ddb3989d9ff259f54581cb1a52501da7fb0864`

정형 토큰·길이·강세가 전체 정확도에 영향을 줍니다. 위 수치는 청취 만족도나 음표 하나의 유일한 음악적 정답 비율을 뜻하지 않습니다. 앞 구절을 사용하는 동작은 같은 평가 목표에서 문맥을 제거하는 검사와 비교했습니다.

학습의 각 epoch·분리된 자료·커버리지·가중치 해시는 `model/results.json`, `run.json`, `epochs.json`에 있습니다. 불확실한 자료가 있던 초기 권리 snapshot과 변환 수정 전 실험은 최종 결과에서 제외했습니다. 최종 가중치는 수정된 자료로 새로 학습했습니다.

## 악보와 청취

대표 32마디 독주: `samples/quiet-day/`. 두 번째 예제: `samples/warm-steps/`. 각각 MIDI, MusicXML, 2쪽 A4 PDF, 실제 PDF에서 렌더링한 PNG, 피아노 MP3를 포함합니다.

형식·화성·A 구절 재현·마지막 으뜸화음과 연주 제약은 명시적인 작곡 보조입니다. 음표 선택에는 새 양손 통합 모델을 사용하며, 노래·드럼·별도 베이스·케이팝 보컬 모델은 사용하지 않습니다. 같은 손의 겹친 두 음은 단순한 협화 음정으로 제한했습니다. 실제 학습 자료 자체를 이런 제약으로 바꾸지는 않았습니다.

각 곡은 32마디, 4/4박자, 4분음표 76으로 약 101초입니다. 청취 파일은 마지막 울림을 포함해 약 104초입니다. TinySoundFont와 TimGM6mb 음색으로 만든 기술 확인용 피아노 렌더링이며 실제 연주 녹음이나 모델이 직접 합성한 오디오는 아닙니다. 관련 라이선스는 `audit/`에 보존했습니다.
