# 오늘도, 나의 자리 — 풍부한 피아노 편곡

[피아노 연주 MP3](sample/piano.mp3) · [가사 포함 악보 PDF](sample/piano/score.pdf) · [피아노 전용 PDF](sample/piano-only/score.pdf)

기존 멜로디·가사를 보존하고 내성 화음, 왼손 반주 리듬, 구간별 밀도를 확장했습니다. 피아노 한 종류만 사용합니다.

- [같은 피아노 음원으로 연주한 기존 편곡](comparison/baseline-same-piano.mp3)
- [악보 그대로 MIDI](sample/piano/score.mid) / [표현·페달 MIDI](sample/performance.mid)
- [학습·데이터·모델·검증 보고서](TRAINING-REPORT.ko.md)
- [검증 기록](verification.json) / [출처와 크레디트](CREDITS.txt)

총1,832개 코퍼스를 학습1,403개·검증199개·평가230개로 나눠 처음부터6에포크 학습했습니다. 배포 가중치는 검증 기준 에포크6입니다. 모델과 데이터는 연구·비상업용 프로필입니다.

`source/training-source.tgz`는 실제 학습 소스 바이트를 보존합니다. 이를 별도 폴더에 풀고 `src`를 PYTHONPATH로 지정하면 엄격한 체크포인트 소스 해시를 유지할 수 있습니다. 실제 연주 처리에는 별도로 동봉한 `source/make_piano_performance.py`가 사용됐으며, 해시는 `sample/performance-source.json`에 있습니다.

원본 개인 이미지, 대형 피아노 SoundFont, 격리한 초기 실험 가중치는 포함하지 않았습니다. 기계적·시각적 검사 기록이며, 직접 청취 선호도나 YouTube 영상과의 유사도를 측정한 결과는 아닙니다.
