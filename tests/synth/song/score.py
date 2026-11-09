"""The score of the synthetic song "Lanterns on the Tide": every musical fact here IS the ground truth.

120 BPM, A minor, 56.5 s, 44.1 kHz stereo.

  t (s)        bar     section            what happens
  0.0-0.5      -       (none)             digital silence (pre-roll)
  0.5          0       (pickup)           one-beat pickup: a snare hit on beat 4 of bar 0 (D12)
  1.0-9.0      1-4     S01 intro          kick + straight hats + pad; tom fill in bar 4
  9.0-17.0     5-8     S02 verse#1        swung groove (8th swing 1.5), syncopated kick/bass, call-and-response V1/V2
  17.0-25.0    9-12    S03 chorus#1       crash + impact, ride, piano arpeggio, duet (V1 lead, V2 harmony = backing)
  25.0-34.5    13-17   S04 bridge#1       EDM build bars 13-16 (snare roll, riser), bar 16 in 3/4, bar 17 digital silence
  34.5-50.5    18-25   S05 chorus#2       the DROP: four-on-the-floor, duet repeat (bars 18-21), instrumental (22-25)
  50.5-56.5    26-28   S06 outro#1        light groove, final hit at 52.5, decay through bar 28 (no pulse)

Times are rounded to the 44.1 kHz sample grid; an event's time is the first sample of its one-shot / note.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "SR",
    "BPM",
    "BEAT",
    "DURATION",
    "N_SAMPLES",
    "Bar",
    "Beat",
    "Section",
    "Phrase",
    "BARS",
    "BEATS",
    "SECTIONS",
    "PHRASES",
    "CHORDS",
    "CHORD_TONES",
    "BASS_ROOT",
    "PATTERNS",
    "BAR_PATTERN",
    "CRASHES",
    "LINES",
    "Line",
    "Word",
    "VOICE_TTS",
    "CHARACTERS",
    "TITLE",
    "ARTIST",
    "ALBUM",
    "snap",
    "step_time",
    "slot_time",
    "bar_of",
    "EDM_ROLES",
    "PULSE_REGIONS",
    "GENERATOR_VERSION",
    "SEED",
    "KEY",
    "PALETTE",
    "ARPABET",
]

GENERATOR_VERSION = "1.0.0"
SEED = 20261108
SR = 44100
BPM = 120.0
BEAT = 60.0 / BPM
DURATION = 56.5
N_SAMPLES = int(round(DURATION * SR))
TITLE, ARTIST, ALBUM = "Lanterns on the Tide", "mv-harness fixture", "Synthetic Sessions"
KEY = {"key": "A minor", "tonic_pc": 9, "mode": "minor"}
PALETTE = ["#1b2a49", "#f2a541", "#3e7cb1", "#c8553d", "#f5f0e1"]  # cover-art blocks, by area (largest first)


def snap(t: float) -> float:
    """Round a time to the 44.1 kHz sample grid (event files then round it to 6 decimals, < 0.5 us)."""
    return round(t * SR) / SR


@dataclass(frozen=True)
class Bar:
    bar: int
    t: float
    beats_in_bar: int  # nominal meter numerator
    n_beats: int  # beats actually in the bar
    pickup: bool
    in_pulse: bool
    swing: float  # long/short 8th ratio (1 = straight)

    @property
    def d(self) -> float:
        return self.n_beats * BEAT

    @property
    def end(self) -> float:
        return self.t + self.d


@dataclass(frozen=True)
class Beat:
    beat_index: int
    t: float
    bar: int
    beat_in_bar: int
    beats_in_bar: int
    in_pulse: bool


def _swing_for(bar: int) -> float:
    if 5 <= bar <= 12 or bar >= 26:
        return 1.5
    return 1.0


def _make_bars() -> list[Bar]:
    bars = [Bar(0, 0.5, 4, 1, True, True, 1.0)]
    for k in range(1, 16):
        bars.append(Bar(k, 1.0 + 2.0 * (k - 1), 4, 4, False, True, _swing_for(k)))
    bars.append(Bar(16, 31.0, 3, 3, False, True, 1.0))
    for k in range(17, 29):
        bars.append(Bar(k, 32.5 + 2.0 * (k - 17), 4, 4, False, k not in (17, 28), _swing_for(k)))
    return bars


BARS: list[Bar] = _make_bars()
BAR = {b.bar: b for b in BARS}


def _make_beats() -> list[Beat]:
    out = []
    for b in BARS:
        first = b.beats_in_bar - b.n_beats + 1 if b.pickup else 1
        for j in range(b.n_beats):
            out.append(Beat(len(out), b.t + j * BEAT, b.bar, first + j, b.beats_in_bar, b.in_pulse))
    return out


BEATS: list[Beat] = _make_beats()
FIRST_BEAT = {b.bar: next(x.beat_index for x in BEATS if x.bar == b.bar) for b in BARS}

#: pulse regions covering [0, DURATION)
PULSE_REGIONS = [
    (0.0, 0.5, False),
    (0.5, 32.5, True),
    (32.5, 34.5, False),
    (34.5, 54.5, True),
    (54.5, 56.5, False),
]


@dataclass(frozen=True)
class Section:
    id: str
    label: str
    occurrence: int
    repeat_group: str
    start_bar: int
    n_bars: int

    @property
    def t(self) -> float:
        return BAR[self.start_bar].t

    @property
    def end(self) -> float:
        return BAR[self.start_bar + self.n_bars - 1].end

    @property
    def d(self) -> float:
        return self.end - self.t

    @property
    def occurrence_label(self) -> str:
        return f"{self.label}#{self.occurrence}"


SECTIONS = [
    Section("S01", "intro", 1, "A", 1, 4),
    Section("S02", "verse", 1, "B", 5, 4),
    Section("S03", "chorus", 1, "C", 9, 4),
    Section("S04", "bridge", 1, "D", 13, 5),
    Section("S05", "chorus", 2, "C", 18, 8),
    Section("S06", "outro", 1, "E", 26, 3),
]


@dataclass(frozen=True)
class Phrase:
    id: str
    start_bar: int
    n_bars: int
    section_id: str


PHRASES = [
    Phrase("P01", 1, 4, "S01"),
    Phrase("P02", 5, 4, "S02"),
    Phrase("P03", 9, 4, "S03"),
    Phrase("P04", 13, 4, "S04"),
    Phrase("P05", 17, 1, "S04"),
    Phrase("P06", 18, 4, "S05"),
    Phrase("P07", 22, 4, "S05"),
    Phrase("P08", 26, 3, "S06"),
]

#: EDM roles (structure stage's canonical definition): (id, role, start_bar, n_bars, section_id)
EDM_ROLES = [("R01", "build", 13, 4, "S04"), ("R02", "drop", 18, 8, "S05")]


def bar_of(t: float) -> int | None:
    for b in BARS:
        if b.t - 1e-9 <= t < b.end - 1e-9:
            return b.bar
    return None


# ------------------------------------------------------------------------------------------------ harmony
#: chord per bar (Harte); bar 0 and the silent bar 17 have no chord ('N'); bars 27-28 hold A minor
CHORDS: dict[int, str] = {}
for _b, _c in zip(range(1, 13), ["A:min", "F:maj", "C:maj", "G:maj"] * 3):
    CHORDS[_b] = _c
CHORDS.update({13: "F:maj", 14: "G:maj", 15: "A:min", 16: "E:maj", 17: "N"})
for _b, _c in zip(range(18, 26), ["A:min", "F:maj", "C:maj", "G:maj"] * 2):
    CHORDS[_b] = _c
CHORDS.update({26: "F:maj", 27: "A:min", 28: "A:min"})

#: pad voicing (MIDI) and bass roots per chord
CHORD_TONES = {
    "A:min": (57, 60, 64),
    "F:maj": (53, 57, 60),
    "C:maj": (55, 60, 64),
    "G:maj": (55, 59, 62),
    "E:maj": (56, 59, 64),
}
BASS_ROOT = {"A:min": 33, "F:maj": 29, "C:maj": 36, "G:maj": 31, "E:maj": 28}
PIANO_TONES = {
    "A:min": (69, 72, 76, 81),
    "F:maj": (65, 69, 72, 77),
    "C:maj": (67, 72, 76, 79),
    "G:maj": (67, 71, 74, 79),
}
ROOT_PC = {"A:min": 9, "F:maj": 5, "C:maj": 0, "G:maj": 7, "E:maj": 4}

# ------------------------------------------------------------------------------------------------ rhythm patterns
#: 16-step patterns: (step, instrument, velocity). Instruments: kick snare tom_hi tom_lo hat hat_open ride
_HATS_STRAIGHT = [(s, "hat", 0.6 if s % 4 == 0 else 0.45) for s in range(0, 16, 2)]
PATTERNS: dict[str, list[tuple[int, str, float]]] = {
    "intro": [(0, "kick", 0.9), (8, "kick", 0.9), *_HATS_STRAIGHT],
    "intro_fill": [
        (0, "kick", 0.9),
        (8, "kick", 0.9),
        *[h for h in _HATS_STRAIGHT if h[0] < 12],
        (12, "tom_hi", 0.8),
        (13, "tom_hi", 0.7),
        (14, "tom_lo", 0.8),
        (15, "tom_lo", 0.75),
    ],
    "verse": [
        (0, "kick", 1.0),
        (7, "kick", 0.8),
        (10, "kick", 0.85),
        (4, "snare", 0.9),
        (12, "snare", 0.9),
        (15, "snare", 0.35),
        *[(s, "hat", 0.6 if s % 4 == 0 else 0.45) for s in range(0, 16, 2)],
    ],
    "chorus": [
        (0, "kick", 0.95),
        (6, "kick", 0.8),
        (8, "kick", 0.9),
        (11, "kick", 0.8),
        (4, "snare", 0.9),
        (12, "snare", 0.9),
        *[(s, "ride", 0.6) for s in (0, 4, 8, 12)],
        *[(s, "hat", 0.5) for s in (2, 6, 10, 14)],
    ],
    "build1": [*[(s, "kick", 0.9) for s in (0, 4, 8, 12)], *[(s, "snare", 0.5) for s in (0, 4, 8, 12)]],
    "build2": [
        *[(s, "kick", 0.9) for s in (0, 4, 8, 12)],
        *[(s, "snare", round(0.55 + 0.02 * s, 3)) for s in range(0, 16, 2)],
    ],
    "build3": [
        *[(s, "kick", 0.9) for s in (0, 4, 8, 12)],
        *[(s, "snare", round(0.5 + 0.02 * s, 3)) for s in range(16)],
    ],
    "build34": [
        *[(s, "kick", 0.95) for s in (0, 4)],
        *[(s, "snare", round(0.7 + 0.03 * s, 3)) for s in range(8)],
        (8, "tom_hi", 0.9),
        (9, "tom_hi", 0.85),
        (10, "tom_lo", 0.9),
        (11, "tom_lo", 0.95),
    ],
    "drop": [
        *[(s, "kick", 1.0) for s in (0, 4, 8, 12)],
        (4, "snare", 0.95),
        (12, "snare", 0.95),
        *[(s, "hat_open", 0.6) for s in (2, 6, 10, 14)],
        *[(s, "hat", 0.35) for s in range(1, 16, 2)],
    ],
    "outro": [
        (0, "kick", 0.85),
        (8, "kick", 0.85),
        (12, "snare", 0.6),
        *[(s, "hat", 0.5 if s % 4 == 0 else 0.4) for s in range(0, 16, 2)],
    ],
    "final": [(0, "kick", 1.0)],
}
BAR_PATTERN: dict[int, str] = {
    1: "intro",
    2: "intro",
    3: "intro",
    4: "intro_fill",
    **{b: "verse" for b in range(5, 9)},
    **{b: "chorus" for b in range(9, 13)},
    13: "build1",
    14: "build2",
    15: "build3",
    16: "build34",
    **{b: "drop" for b in range(18, 26)},
    26: "outro",
    27: "final",
}
#: groove ids by pattern (order of first appearance)
GROOVE_IDS = {
    name: f"G{i:02d}"
    for i, name in enumerate(dict.fromkeys(BAR_PATTERN[b] for b in sorted(BAR_PATTERN)), start=1)
}
#: crash accents on top of the patterns: bar -> (velocity, length s)
CRASHES = {9: (0.9, 2.5), 18: (1.0, 2.5), 22: (0.8, 2.0), 27: (1.0, 4.0)}
PICKUP_HITS = [(0, "snare", 0.75)]  # bar 0, at its single beat


def section_vel(bar: int | None) -> float:
    """Velocity scale of drums and bass: the drop (bars 18-25) and the final hit (bar 27) hit hardest."""
    return 1.0 if bar is not None and (18 <= bar <= 25 or bar == 27) else 0.78


#: drum instrument -> (drum class for events/drum_hits.json, DrumSep sub-stem)
DRUM_MAP = {
    "kick": ("kick", "kick"),
    "snare": ("snare", "snare"),
    "tom_hi": ("tom", "toms"),
    "tom_lo": ("tom", "toms"),
    "hat": ("hat", "hihat"),
    "hat_open": ("hat", "hihat"),
    "ride": ("cymbal", "ride"),
    "crash": ("cymbal", "crash"),
}
#: groove-matrix row of each instrument (grooves.json rows kick, snare, hat, perc)
GROOVE_ROW = {
    "kick": "kick",
    "snare": "snare",
    "hat": "hat",
    "hat_open": "hat",
    "ride": "hat",
    "tom_hi": "perc",
    "tom_lo": "perc",
    "crash": "perc",
}


def swing_frac(p: float, ratio: float) -> float:
    """Map a position p in [0, 1) of a beat to swung time (8th swing: the off-8th lands at r/(1+r))."""
    sw = ratio / (1.0 + ratio)
    return p * 2 * sw if p <= 0.5 else sw + (p - 0.5) * 2 * (1 - sw)


def step_time(bar: int, step: float) -> float:
    """Time of 16th step `step` (may exceed the bar: continues into following bars) with the bar's swing."""
    b = BAR[bar]
    beat, frac = divmod(step / 4.0, 1.0)
    while beat >= b.n_beats and b.bar + 1 in BAR:
        beat -= b.n_beats
        b = BAR[b.bar + 1]
    return snap(b.t + (beat + swing_frac(frac, b.swing)) * BEAT)


def slot_time(bar: int, slot: float) -> float:
    """Time of 8th slot `slot` counted from bar `bar` (swung)."""
    return step_time(bar, slot * 2)


# ------------------------------------------------------------------------------------------------ vocals
VOICE_TTS = {"V1": "david", "V2": "zira"}
CHARACTERS = {
    "C1": {
        "name": "The Lamplighter",
        "voice": "V1",
        "lead_backing": "lead",
        "description": "a low, steady voice who carries light along the river (synthetic fixture character)",
    },
    "C2": {
        "name": "The Tide",
        "voice": "V2",
        "lead_backing": "both",
        "description": "a high voice that answers the Lamplighter and harmonises in the choruses (synthetic fixture character)",
    },
}


@dataclass(frozen=True)
class Word:
    text: str
    slot: int  # 8th slot from the line's bar
    slots: int  # length in 8th slots
    midi: int
    harmony: int | None = None  # backing (V2) note in duet lines


@dataclass(frozen=True)
class Line:
    id: str
    bar: int
    voice: str  # lead voice
    words: tuple[Word, ...]
    duet: bool = False  # V2 sings `harmony` notes on backing_vocals at the same time
    section_id: str = ""
    text_group: str = ""
    repeat_group: str | None = None

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def _w(spec):
    return tuple(Word(*s) for s in spec)


_L005 = _w(
    [
        ("We", 0, 1, 57, 60),
        ("are", 1, 1, 60, 64),
        ("the", 2, 1, 62, 65),
        ("echo", 3, 3, 64, 67),
        ("of", 6, 1, 62, 65),
        ("the", 7, 1, 60, 64),
        ("morning", 8, 6, 57, 60),
    ]
)
_L006 = _w(
    [
        ("We", 0, 1, 57, 60),
        ("will", 1, 1, 59, 62),
        ("rise", 2, 2, 60, 64),
        ("when", 4, 1, 62, 65),
        ("the", 5, 1, 62, 65),
        ("tide", 6, 2, 64, 67),
        ("comes", 8, 2, 62, 65),
        ("in", 10, 4, 59, 62),
    ]
)
LINES: list[Line] = [
    Line(
        "L001",
        5,
        "V1",
        _w(
            [
                ("Paper", 0, 2, 57),
                ("lanterns", 2, 2, 60),
                ("over", 4, 1, 59),
                ("the", 5, 1, 57),
                ("river", 6, 2, 55),
            ]
        ),
        section_id="S02",
        text_group="T01",
    ),
    Line(
        "L002",
        6,
        "V2",
        _w([("Carry", 1, 2, 69), ("the", 3, 1, 67), ("light", 4, 4, 64)]),
        section_id="S02",
        text_group="T02",
    ),
    Line(
        "L003",
        7,
        "V1",
        _w(
            [
                ("Copper", 0, 2, 57),
                ("bells", 2, 2, 60),
                ("along", 4, 1, 62),
                ("the", 5, 1, 60),
                ("harbor", 6, 2, 57),
            ]
        ),
        section_id="S02",
        text_group="T03",
    ),
    Line(
        "L004",
        8,
        "V2",
        _w([("Ring", 1, 2, 69), ("through", 3, 1, 67), ("the", 4, 1, 65), ("night", 5, 3, 64)]),
        section_id="S02",
        text_group="T04",
    ),
    Line("L005", 9, "V1", _L005, duet=True, section_id="S03", text_group="T05", repeat_group="LG01"),
    Line("L006", 11, "V1", _L006, duet=True, section_id="S03", text_group="T06", repeat_group="LG02"),
    Line(
        "L007",
        13,
        "V2",
        _w([("Hold", 0, 2, 69), ("your", 2, 1, 67), ("breath", 3, 5, 65)]),
        section_id="S04",
        text_group="T07",
    ),
    Line(
        "L008",
        15,
        "V1",
        _w([("Here", 0, 2, 57), ("it", 2, 1, 59), ("comes", 3, 5, 64)]),
        section_id="S04",
        text_group="T08",
    ),
    Line("L009", 18, "V1", _L005, duet=True, section_id="S05", text_group="T05", repeat_group="LG01"),
    Line("L010", 20, "V1", _L006, duet=True, section_id="S05", text_group="T06", repeat_group="LG02"),
]
WORD_GAP_S = 0.03  # silence between a word's end and the next slot

#: hand-written ARPAbet for every lyric word (used for the synthetic phoneme/viseme tracks)
ARPABET = {
    "paper": "P EY1 P ER0",
    "lanterns": "L AE1 N T ER0 N Z",
    "over": "OW1 V ER0",
    "the": "DH AH0",
    "river": "R IH1 V ER0",
    "carry": "K AE1 R IY0",
    "light": "L AY1 T",
    "copper": "K AA1 P ER0",
    "bells": "B EH1 L Z",
    "along": "AH0 L AO1 NG",
    "harbor": "HH AA1 R B ER0",
    "ring": "R IH1 NG",
    "through": "TH R UW1",
    "night": "N AY1 T",
    "we": "W IY1",
    "are": "AA1 R",
    "echo": "EH1 K OW0",
    "of": "AH1 V",
    "morning": "M AO1 R N IH0 NG",
    "will": "W IH1 L",
    "rise": "R AY1 Z",
    "when": "W EH1 N",
    "tide": "T AY1 D",
    "comes": "K AH1 M Z",
    "in": "IH1 N",
    "hold": "HH OW1 L D",
    "your": "Y AO1 R",
    "breath": "B R EH1 TH",
    "here": "HH IY1 R",
    "it": "IH1 T",
}


@dataclass
class Truth:
    """Filled by render.py: every rendered event with exact sample-grid times."""

    drum_hits: list[dict] = field(default_factory=list)
    notes: dict[str, list[dict]] = field(default_factory=dict)
    words: list[dict] = field(default_factory=list)
    backing_words: list[dict] = field(default_factory=list)
