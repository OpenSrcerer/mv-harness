# ruff: noqa: E501  (long numeric tables / docstrings)
"""The instrument vocabulary of the instruments stage (owner M3b).

Each slug is evidenced by CED (AudioSet) labels measured on the mix and on its candidate stems, and, for the stems the
separator dedicates to it (``anchor``), by stem activity. ``stem_weight`` is how much a dedicated stem alone is
believed without the tagger (the separators are trained for drums and bass; a ``vocals`` stem also catches synth leads,
docs/SPIKE.md, so voice needs the tagger). ``parent`` slugs gate sub-types (``electric_guitar`` needs ``guitar``).

The vocabulary is open (CONTRACT §13): slugs match ``^[a-z0-9_]+$``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Inst:
    slug: str
    labels: tuple[str, ...]                 # CED labels (max over them)
    stems: tuple[str, ...] = ()             # stems the tagger is also run on (besides the mix)
    anchor: str | None = None               # dedicated separator stem (stem-activity evidence)
    stem_weight: float = 0.0                # belief in an active anchor stem without tagger support
    parent: str | None = None               # sub-type of this slug
    lo: float = 0.03                        # tagger probability mapped to 0 evidence
    hi: float = 0.30                        # tagger probability mapped to full evidence
    mix_weight: float = 1.0                 # trust in the tag measured on the full mix
    group: str = "instrument"               # instrument | voice | fx
    clap: tuple[str, ...] = field(default_factory=tuple)


SINGING = ("Singing", "Male singing", "Female singing", "Child singing", "Synthetic singing", "Humming", "Yodeling",
           "A capella", "Choir")
SPEECH = ("Speech", "Male speech", "Female speech", "Child speech", "Narration", "Conversation", "Whispering", "Shout",
          "Yell")
RAP = ("Rapping",)
VOICE = SINGING + SPEECH + RAP + ("Chant", "Vocal music", "Beatboxing")

VOCAB: tuple[Inst, ...] = (
    Inst("voice", VOICE, ("vocals", "lead_vocals"), "vocals", 0.2, lo=0.04, hi=0.25, mix_weight=0.6, group="voice"),
    Inst("choir", ("Choir", "Chant", "Mantra"), ("vocals", "backing_vocals"), None, parent="voice", hi=0.25, group="voice"),
    Inst("beatbox", ("Beatboxing",), ("vocals",), None, parent="voice", lo=0.05, hi=0.3, group="voice"),
    Inst("drums", ("Drum kit", "Drum", "Snare drum", "Bass drum", "Drum roll", "Rimshot", "Cymbal", "Hi-hat", "Percussion",
                   "Drum machine"), ("drums",), "drums", 0.7, lo=0.05, hi=0.35),
    Inst("drum_machine", ("Drum machine",), ("drums",), None, parent="drums", lo=0.04, hi=0.3),
    Inst("percussion", ("Tambourine", "Maraca", "Rattle (instrument)", "Wood block", "Cowbell", "Tabla", "Timpani", "Gong",
                        "Clapping", "Finger snapping"), ("drums", "other"), None, lo=0.05, hi=0.3),
    Inst("bass", ("Bass guitar", "Double bass"), ("bass",), "bass", 0.7, lo=0.03, hi=0.25, mix_weight=0.5),
    Inst("guitar", ("Guitar", "Electric guitar", "Acoustic guitar", "Steel guitar", "Plucked string instrument", "Strum",
                    "Tapping (guitar technique)"), ("guitar", "other"), "guitar", 0.45, lo=0.05, hi=0.35),
    Inst("electric_guitar", ("Electric guitar",), ("guitar", "other"), None, parent="guitar", lo=0.03, hi=0.25),
    Inst("distorted_guitar", ("Distortion", "Heavy metal", "Grunge", "Punk rock"), ("guitar",), None, parent="guitar",
         lo=0.05, hi=0.3),
    Inst("acoustic_guitar", ("Acoustic guitar", "Steel guitar", "Strum"), ("guitar", "other"), None, parent="guitar",
         lo=0.04, hi=0.3),
    Inst("folk_strings", ("Banjo", "Mandolin", "Ukulele", "Sitar", "Zither"), ("guitar", "other"), None, lo=0.05, hi=0.3),
    Inst("piano", ("Piano",), ("piano", "other"), "piano", 0.3, lo=0.04, hi=0.3),
    Inst("electric_piano", ("Electric piano",), ("piano", "other"), None, lo=0.04, hi=0.3),
    Inst("organ", ("Organ", "Electronic organ", "Hammond organ"), ("piano", "other"), None, lo=0.04, hi=0.3),
    Inst("harpsichord", ("Harpsichord",), ("piano", "other"), None, lo=0.05, hi=0.3),
    Inst("synth", ("Synthesizer", "Sampler", "Theremin"), ("other", "piano", "bass", "vocals"), None, lo=0.04, hi=0.3),
    Inst("synth_fx", ("Sound effect", "Whoosh", "Effects unit", "Chirp tone", "Sine wave", "Zing", "Boing"), ("other",),
         None, lo=0.05, hi=0.35, mix_weight=0.5, group="fx"),
    Inst("strings", ("Bowed string instrument", "String section", "Violin", "Cello", "Double bass", "Pizzicato",
                     "Orchestra"), ("other",), None, lo=0.04, hi=0.3),
    Inst("brass", ("Brass instrument", "French horn", "Trumpet", "Trombone"), ("other",), None, lo=0.04, hi=0.3),
    Inst("woodwinds", ("Wind instrument", "Flute", "Clarinet"), ("other",), None, lo=0.04, hi=0.3),
    Inst("saxophone", ("Saxophone",), ("other",), None, lo=0.04, hi=0.3),
    Inst("mallets", ("Mallet percussion", "Marimba", "Glockenspiel", "Vibraphone", "Steelpan"), ("other", "piano"), None,
         lo=0.04, hi=0.3),
    Inst("bells", ("Bell", "Chime", "Tubular bells", "Wind chime", "Church bell", "Jingle bell"), ("other",), None,
         lo=0.05, hi=0.3),
    Inst("harp", ("Harp",), ("other", "piano"), None, lo=0.04, hi=0.3),
    Inst("harmonica", ("Harmonica",), ("other",), None, lo=0.04, hi=0.3),
    Inst("accordion", ("Accordion", "Bagpipes"), ("other",), None, lo=0.04, hi=0.3),
    Inst("turntable", ("Scratching (performance technique)",), ("other", "drums"), None, lo=0.05, hi=0.3),
)
BY_SLUG = {i.slug: i for i in VOCAB}

#: CLAP sub-types of ``synth`` (relative curves only: CLAP is never a top-1 label, docs/SPIKE.md)
SYNTH_SUBTYPES: dict[str, str] = {
    "synth_pad": "a soft sustained synthesizer pad",
    "synth_lead": "a bright lead synthesizer melody",
    "synth_arp": "an arpeggiated synthesizer sequence",
    "synth_bass": "a deep synth bass line",
}
#: neutral prompts: the CLAP baseline that relative scores are measured against
CLAP_NEUTRAL = ("a sound", "music", "noise", "a recording")

#: CED labels reported in meta/instruments.json top_tags are drawn from these (genre/scene labels excluded)
STYLE_LABELS = {"singing": SINGING, "speech": SPEECH, "rap": RAP}
HIPHOP_CONTEXT = ("Rapping", "Hip hop music")
