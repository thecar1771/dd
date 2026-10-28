"""Measure the actual rendered backing WAV; no subjective listening claim."""
import array
import json
import math
from pathlib import Path
import sys
import wave

root = Path(sys.argv[1])
with wave.open(str(root / 'piano/backing.wav'), 'rb') as wav:
    rate, channels, width, frames = wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()
    assert (rate, channels, width) == (44100, 2, 2)
    samples = array.array('h', wav.readframes(frames))
if sys.byteorder != 'little':
    samples.byteswap()
peak = max(abs(s) for s in samples)
rms = math.sqrt(sum(s * s for s in samples) / len(samples))
assert abs(frames / rate - 83) < .01
assert 0 < peak < 32760 and rms > 0
report = dict(sample_rate=rate, channels=channels, seconds=frames / rate,
              sample_peak=peak, peak_dbfs=round(20 * math.log10(peak / 32768), 3),
              rms_dbfs=round(20 * math.log10(rms / 32768), 3),
              clipped_samples=sum(abs(s) >= 32767 for s in samples),
              scope='piano accompaniment only; no synthesized rap vocal')
(root / 'audio-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
