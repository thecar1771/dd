"""Expressive playback must still operate one physical piano keyboard."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

import mido
import pytest


@pytest.fixture(scope="module")
def performance():
    path = Path(__file__).resolve().parents[2] / "scripts" / "make_piano_performance.py"
    spec = importlib.util.spec_from_file_location("piano_performance_regressions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_handoff(path, earlier_track=0, overlap=False):
    midi = mido.MidiFile(type=1, ticks_per_beat=120)
    for track_index in range(2):
        start = 0 if track_index == earlier_track else (60 if overlap else 120)
        midi.tracks.append(mido.MidiTrack([
            mido.Message("program_change", channel=track_index, program=0),
            mido.Message("note_on", channel=track_index, note=60, velocity=70, time=start),
            mido.Message("note_off", channel=track_index, note=60, time=120),
            mido.MetaMessage("end_of_track"),
        ]))
    midi.save(path)


def read_physical_playback(path):
    midi = mido.MidiFile(path)
    tick = 0
    active = {}
    physical = {}
    inventory = Counter()
    notes = []
    pedals = {}
    for message in mido.merge_tracks(midi.tracks):
        tick += message.time
        if message.type == "note_on" and message.velocity:
            key = (message.channel, message.note)
            assert message.note not in physical, ("physical key overlap", tick, message.note)
            assert key not in active
            active[key] = tick
            physical[message.note] = key
            inventory[key] += 1
        elif message.type in ("note_on", "note_off"):
            key = (message.channel, message.note)
            start = active.pop(key)
            assert physical.pop(message.note) == key
            assert tick > start
            notes.append((key, start, tick))
        elif message.type == "control_change" and message.control == 64:
            pedals[message.channel] = message.value
    assert not active and not physical
    return inventory, notes, pedals


@pytest.mark.parametrize("seed", range(1, 13))
@pytest.mark.parametrize("earlier_track", [0, 1])
def test_humanized_cross_channel_handoff_never_overlaps_physical_key(
    performance, tmp_path, seed, earlier_track,
):
    source = tmp_path / "score.mid"
    output = tmp_path / "performance.mid"
    write_handoff(source, earlier_track)
    original = source.read_bytes()

    performance.transform(source, output, seed=seed)

    inventory, notes, pedals = read_physical_playback(output)
    assert inventory == Counter({(0, 60): 1, (1, 60): 1})
    assert len(notes) == 2
    assert pedals == {0: 0, 1: 0}
    assert source.read_bytes() == original
    report = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert report["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert report["performance_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert report["seed"] == seed and report["notes"] == 2
    assert report["source_midi_unchanged"] and report["pitch_inventory_unchanged"]
    assert report["no_hanging_notes"] and report["final_pedal_released"]
    assert sorted((n[1], n[2] - n[1]) for n in notes) == sorted(
        (change["played_onset"], change["played_duration"]) for change in report["changes"]
    )


def test_performance_seed_reproduces_midi_and_change_trace(performance, tmp_path):
    source = tmp_path / "score.mid"
    write_handoff(source)
    outputs = [tmp_path / name for name in ("first.mid", "second.mid")]
    for output in outputs:
        performance.transform(source, output, seed=6)
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    reports = [json.loads(path.with_suffix(".json").read_text(encoding="utf-8")) for path in outputs]
    assert reports[0] == reports[1]


def test_source_overlap_across_channels_is_rejected_without_output(performance, tmp_path):
    source = tmp_path / "overlap.mid"
    output = tmp_path / "performance.mid"
    write_handoff(source, overlap=True)
    original = source.read_bytes()
    with pytest.raises(ValueError, match="physical.*overlap|overlap.*physical"):
        performance.transform(source, output, seed=1)
    assert source.read_bytes() == original
    assert not output.exists() and not output.with_suffix(".json").exists()
