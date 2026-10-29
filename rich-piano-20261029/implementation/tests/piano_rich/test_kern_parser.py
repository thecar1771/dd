"""Independent Kern signatures; no downloaded corpus or music21 is required."""
from fractions import Fraction as F
import importlib.util
from pathlib import Path

import pytest

from omr.piano_rich.tokenizer import RichPianoTokenizer


@pytest.fixture(scope="module")
def kern():
    path = Path(__file__).resolve().parents[2] / "scripts" / "collect_rich_piano.py"
    spec = importlib.util.spec_from_file_location("rich_piano_kern_regressions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tied_chord_members_inherit_dotted_duration(kern):
    # Reduced from Antoinette's [4.a [f# [d signature. All three chord
    # members sustain through the continuation, rather than being reattacked.
    parsed = kern.parse_kern(
        "**kern\t**kern\n"
        "*staff2\t*staff1\n"
        "*M3/4\t*M3/4\n"
        "=1\t=1\n"
        "2.C\t[4.a [f# [d\n"
        ".\t4.a] f#] d]\n"
        "=2\t=2\n"
        "*-\t*-\n"
    )
    upper = sorted(tuple(note[:3]) for note in parsed["notes"] if note[3] == 1)
    assert upper == [(F(0), F(3), pitch) for pitch in (62, 66, 69)]
    bars, _, _ = kern.kern_bars(parsed)
    assert len(bars) == 1 and bars[0]["length"] == 36
    assert {tuple(note[:3]) for note in bars[0]["notes"]} == {
        (0, 36, pitch) for pitch in (48, 62, 66, 69)
    }
    assert bars[0]["tie"] == [0, 0, 0, 0]


@pytest.mark.parametrize(
    "token,pitch",
    [
        ("[2.B", 59),  # B3, not lowercase b (B4) or bb (B5).
        ("[2.B-", 58),
        ("[2.B#", 60),
        ("4Bn", 59),
        ("4b", 71),
        ("4bb", 83),
        ("8BB^^-L", 46),  # Accidentals need not immediately follow letters.
        ("16b]-", 70),
    ],
)
def test_kern_letter_case_and_accidentals_preserve_pitch(kern, token, pitch):
    assert kern.kern_pitch(token) == pitch


def test_split_spine_chord_keeps_both_octaves_and_independent_voice_time(kern):
    # Cleopha's 2ccc cc chord must contain C6 and C5 together while the
    # other upper-staff voice advances in quarter notes.
    parsed = kern.parse_kern(
        "**kern\t**kern\n"
        "*staff2\t*staff1\n"
        "*M2/4\t*M2/4\n"
        "=1\t=1\n"
        "*\t*^\n"
        "2C\t2ccc cc\t4ff\n"
        ".\t.\t4ee\n"
        "=2\t=2\t=2\n"
        "*\t*v\t*v\n"
        "*-\t*-\n"
    )
    assert sorted(tuple(note) for note in parsed["notes"]) == sorted(
        [
            (F(0), F(2), 48, 2, 0),
            (F(0), F(2), 72, 1, 0),
            (F(0), F(2), 84, 1, 0),
            (F(0), F(1), 77, 1, 1),
            (F(1), F(1), 76, 1, 1),
        ]
    )
    bars, _, _ = kern.kern_bars(parsed)
    assert len(bars) == 1 and bars[0]["length"] == 24
    assert [note[:3] for note in bars[0]["notes"]] == [
        [0, 24, 48], [0, 24, 72], [0, 12, 77], [0, 24, 84], [12, 12, 76]
    ]


def test_explicit_staff_labels_override_spine_order_and_pitch_cutoff(kern):
    # Deliberately reverse conventional spine order and cross the hands.
    parsed = kern.parse_kern(
        "**kern\t**kern\n"
        "*staff1\t*staff2\n"
        "*M1/4\t*M1/4\n"
        "=1\t=1\n"
        "4G\t4e\n"
        "=2\t=2\n"
        "*-\t*-\n"
    )
    assert {(note[2], note[3]) for note in parsed["notes"]} == {(55, 1), (64, 2)}
    bars, _, _ = kern.kern_bars(parsed)
    tok = RichPianoTokenizer()
    encoded = tok.encode_bar(
        dict(length=12, notes=bars[0]["notes"], note_staff=bars[0]["staff"])
    )
    assert tok.decode_bar(encoded)["roles"] == ["melody", "bass"]


def test_cross_bar_segments_encode_as_new_and_held_attacks(kern):
    parsed = kern.parse_kern(
        "**kern\t**kern\n"
        "*staff2\t*staff1\n"
        "*M4/4\t*M4/4\n"
        "=1\t=1\n"
        "[1C\t1c\n"
        "=2\t=2\n"
        "1C]\t1d\n"
        "=3\t=3\n"
        "*-\t*-\n"
    )
    bars, _, _ = kern.kern_bars(parsed)
    assert [bar["length"] for bar in bars] == [48, 48]
    assert [bar["tie"] for bar in bars] == [[0, 0], [1, 0]]
    tok = RichPianoTokenizer()
    adapted = []
    for bar in bars:
        # Final-data adapter contract: only exact 0/1 continuation evidence
        # becomes bool; ambiguous source evidence must be withheld upstream.
        assert all(type(flag) in (int, bool) and flag in (0, 1) for flag in bar["tie"])
        adapted.append(dict(
            length=bar["length"], notes=bar["notes"], note_staff=bar["staff"],
            note_tie_from_previous_bar=[bool(flag) for flag in bar["tie"]],
        ))
    assert [tok.decode_bar(tok.encode_bar(bar))["attacks"] for bar in adapted] == [
        ["new", "new"], ["held", "new"]
    ]
    targets = [tok.tokens[token] for ids, mask in tok.windows(dict(bars=adapted))
               for token, scored in zip(ids, mask) if scored]
    assert targets.count("ATTACK_new") == 3
    assert targets.count("ATTACK_held") == 1
    assert "ATTACK_unknown" not in targets
