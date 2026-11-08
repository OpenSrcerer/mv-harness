# ruff: noqa: E501  (long catalogue tables / docstrings)
"""The output catalogue: every file, every events name, their frozen fields, and the Consumed-by matrix.

FROZEN at contract v1 (PLAN §4.6): the envelope schemas, IDs, time/unit conventions and every field marked
required here (required == frozen: producers must write it; consumers may rely on it). Producers may add
optional fields (minor version bump, noted in their report). Removing or renaming a required field, or
changing its unit/type, needs a change request.

This module is the single source for:
  * src/mvh/contract/schema/**.schema.json   (python -m mvh.contract.gen)
  * the generated tables in docs/CONTRACT.md  (same command)
  * the outputs of the stage stubs            (outputs_for(stage))
Stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ids import DRUM_SUBSTEMS, ID_KINDS, PITCHED_SOURCES, STEM_NAMES
from .registry import CHANNELS, CURVE_FILES

CONTRACT_VERSION = "1.0.0-rc.1"
SCHEMA_BASE = "https://mv-harness.local/schema/"

# ============================================================================ schema building blocks
U = "x-unit"


def num(unit: str | None = None, desc: str = "", minimum: float | None = None, maximum: float | None = None) -> dict:
    s: dict[str, Any] = {"type": "number"}
    if unit:
        s[U] = unit
    if desc:
        s["description"] = desc
    if minimum is not None:
        s["minimum"] = minimum
    if maximum is not None:
        s["maximum"] = maximum
    return s


def integer(desc: str = "", minimum: int | None = None, maximum: int | None = None, unit: str | None = None) -> dict:
    s: dict[str, Any] = {"type": "integer"}
    if unit:
        s[U] = unit
    if desc:
        s["description"] = desc
    if minimum is not None:
        s["minimum"] = minimum
    if maximum is not None:
        s["maximum"] = maximum
    return s


def string(desc: str = "", pattern: str | None = None, enum: list[str] | None = None) -> dict:
    s: dict[str, Any] = {"type": "string"}
    if desc:
        s["description"] = desc
    if pattern:
        s["pattern"] = pattern
    if enum:
        s["enum"] = list(enum)
    return s


def boolean(desc: str = "") -> dict:
    s: dict[str, Any] = {"type": "boolean"}
    if desc:
        s["description"] = desc
    return s


def idref(kind: str, desc: str = "") -> dict:
    return string(desc or f"{ID_KINDS[kind].entity} id", pattern=ID_KINDS[kind].regex)


def arr(items: dict, desc: str = "", min_items: int | None = None, max_items: int | None = None) -> dict:
    s: dict[str, Any] = {"type": "array", "items": items}
    if desc:
        s["description"] = desc
    if min_items is not None:
        s["minItems"] = min_items
    if max_items is not None:
        s["maxItems"] = max_items
    return s


def obj(req: dict | None = None, opt: dict | None = None, desc: str = "", additional: bool | dict = True) -> dict:
    props = dict(req or {})
    props.update(opt or {})
    s: dict[str, Any] = {"type": "object", "properties": props, "required": sorted(req or {})}
    if desc:
        s["description"] = desc
    if additional is not True:
        s["additionalProperties"] = additional
    return s


def mapof(values: dict, desc: str = "", keys: str | None = None) -> dict:
    s: dict[str, Any] = {"type": "object", "additionalProperties": values}
    if keys:
        s["propertyNames"] = {"pattern": keys}
    if desc:
        s["description"] = desc
    return s


def nullable(s: dict) -> dict:
    s = dict(s)
    t = s.get("type")
    if isinstance(t, str):
        s["type"] = [t, "null"]
    if "enum" in s:
        s["enum"] = list(s["enum"]) + [None]
    return s


def ref(schema_id: str) -> dict:
    return {"$ref": SCHEMA_BASE + schema_id + ".schema.json"}


T = num("s", "time in seconds from the first sample of audio/mix.flac")
D = num("s", "duration in seconds", minimum=0)
P01 = num("0..1", minimum=0, maximum=1)
HEX = string("colour as #rrggbb", pattern=r"^#[0-9a-fA-F]{6}$")
PC = integer("pitch class, C = 0", minimum=0, maximum=11)
SHA = string("sha256 (hex)", pattern=r"^[0-9a-f]{64}$")
SEMVER = string("semver", pattern=r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")
SOURCE_REF = obj({"file": string("path relative to the song folder"),
                  "id": string("item id, or a reference key 'beat:<beat_index>' / 'bar:<bar>'")},
                 desc="link to the item a derived item comes from")
STEM_ENUM = list(STEM_NAMES) + [f"drums_{s}" for s in DRUM_SUBSTEMS]
GRADE = string("A (best) .. D", enum=["A", "B", "C", "D"])
CLAIM_SOURCE = string("who/what supports the claim; precedence user > lyric > audio > external > speculative",
                      enum=["user", "lyric", "audio", "external", "speculative"])
CITE = obj(opt={"id": string("a cited ID (L001, S03, Q0012, ...)"), "t0": num("s"), "t1": num("s"),
                "quote": string("at most 10 words")}, desc="citation: an ID and/or a time range")
CLAIM_PROV = obj({"source": CLAIM_SOURCE, "status": string(enum=["user", "draft"]), "cites": arr(CITE)})
CLAIM = obj({"text": string(), "source": CLAIM_SOURCE, "cites": arr(CITE)}, opt={"status": string(enum=["user", "draft"])})


# ============================================================================ events
@dataclass(frozen=True)
class Field:
    name: str
    schema: dict
    required: bool = True

    @property
    def unit(self) -> str | None:
        s = self.schema
        return s.get(U) or (s.get("items", {}) or {}).get(U)

    @property
    def type(self) -> str:
        s = self.schema
        t = s.get("type", "object")
        if isinstance(t, list):
            t = "|".join(t)
        if "pattern" in s and s.get("description", "").endswith(" id"):
            return "id"
        if "enum" in s:
            return "enum"
        return t


def F(name: str, schema: dict, required: bool = True) -> Field:
    return Field(name, schema, required)


@dataclass(frozen=True)
class EventDef:
    name: str              # events name (may hold {src})
    stage: str
    kind: str              # 'event' | 'segment'
    fields: tuple[Field, ...]
    description: str
    path: str = ""         # default events/<name>.json
    schema: str = ""       # default events/<name>
    id_kind: str | None = None
    required: bool = True  # is the file always written

    @property
    def file(self) -> str:
        return self.path or f"events/{self.name}.json"

    @property
    def schema_id(self) -> str:
        return self.schema or f"events/{self.name}"


def _ev(name, stage, kind, fields, description, **kw) -> EventDef:
    return EventDef(name, stage, kind, tuple(fields), description, **kw)


_HIT_FIELDS = [F("t", T), F("t_peak", num("s", "time of the envelope peak")), F("strength", num("0..1+", "1 ~ a typical hit", minimum=0)),
               F("db", num("dBFS", "band level at the peak"))]
_NOTE_FIELDS = [F("t", T), F("d", D), F("midi", integer("MIDI note number", 0, 127)), F("name", string("note name, e.g. A3 (C4 = MIDI 60)")),
                F("vel", P01 | {"description": "velocity 0..1"}), F("conf", P01)]

EVENTS: list[EventDef] = [
    # ---------------------------------------------------------------- spectral
    *[_ev(f"hits.{b}", "spectral", "event", _HIT_FIELDS, f"{b} hit events from the viz hit envelope (refined on a 2.5 ms envelope)")
      for b in ("kick", "mid", "high")],
    *[_ev(f"onsets.{b}", "spectral", "event", [F("t", T), F("strength", P01)], f"{b}-band flux onsets (centred threshold)")
      for b in ("bass", "mid", "high")],
    # ---------------------------------------------------------------- rhythm
    _ev("beats", "rhythm", "event", [
        F("beat_index", integer("0-based; equals the item's position", minimum=0)), F("t", T),
        F("bar", integer("1-based bar; 0 = pickup bar", minimum=0)), F("beat_in_bar", integer("1..beats_in_bar", minimum=1)),
        F("beats_in_bar", integer("nominal beats in this beat's bar", minimum=1)),
        F("in_pulse", boolean("false for virtual-grid beats in no-pulse regions")),
        F("strength", P01 | {"description": "tracker activation at the beat"}), F("conf", P01),
    ], "the beat grid: every beat, virtual beats (in_pulse false) continue through no-pulse regions"),
    _ev("bars", "rhythm", "segment", [
        F("bar", integer("1-based; 0 = pickup", minimum=0)), F("t", T), F("d", D),
        F("beats_in_bar", integer("nominal (meter numerator)", minimum=1)), F("n_beats", integer("beats actually in this bar", minimum=1)),
        F("first_beat", integer("beat_index of the bar's first beat", minimum=0)), F("pickup", boolean()), F("in_pulse", boolean()),
        F("conf", P01),
    ], "bars (downbeat to downbeat); section/phrase/groove links are in tables/bars.csv"),
    _ev("tempo_segments", "rhythm", "segment", [F("t", T), F("d", D), F("bpm", num("BPM")), F("stable", boolean())],
        "piecewise tempo grid"),
    _ev("pulse_regions", "rhythm", "segment", [F("t", T), F("d", D), F("in_pulse", boolean())],
        "regions with / without a perceptible beat, covering the whole song"),
    # ---------------------------------------------------------------- harmony
    _ev("key", "harmony", "segment", [F("t", T), F("d", D), F("key", string("e.g. 'A minor'")), F("tonic_pc", PC),
                                      F("mode", string(enum=["major", "minor"])), F("conf", P01), F("agree", boolean("methods agree"))],
        "key regions (one item when the key never changes)"),
    _ev("chords", "harmony", "segment", [F("t", T), F("d", D), F("label", string("Harte-style label, e.g. 'A:min', 'N' for no chord")),
                                         F("root_pc", nullable(PC)), F("quality", string("maj, min, 7, maj7, min7, dim, aug, sus2, sus4, N, ...")),
                                         F("bass_pc", nullable(PC)), F("conf", P01),
                                         F("beat_index", nullable(integer("beat the chord starts on", minimum=0)))],
        "chord timeline snapped to beats"),
    # ---------------------------------------------------------------- dynamics
    _ev("dynamics", "dynamics", "segment", [F("t", T), F("d", D),
                                            F("level", string(enum=["silence", "quiet", "soft", "medium", "loud", "peak"])),
                                            F("rel_lu", num("LU", "mean short-term loudness relative to integrated")),
                                            F("mean_lufs", num("LUFS")), F("conf", P01)],
        "loud and quiet parts, boundaries snapped to downbeats"),
    _ev("impacts", "dynamics", "event", [F("id", idref("impact")), F("t", T), F("strength", P01), F("delta_lu", num("LU")),
                                         F("delta_bass_db", num("dB")), F("bar", nullable(integer(minimum=0)))],
        "sudden energy increases", id_kind="impact"),
    _ev("stops", "dynamics", "event", [F("id", idref("stop")), F("t", T), F("strength", P01), F("gap_s", num("s", minimum=0))],
        "sudden cuts to (near) silence", id_kind="stop"),
    _ev("silences", "dynamics", "segment", [F("id", idref("silence")), F("t", T), F("d", D), F("depth_db", num("dB", "below integrated loudness"))],
        "silent stretches", id_kind="silence"),
    _ev("decay_tails", "dynamics", "segment", [F("id", idref("decay_tail")), F("t", T), F("d", D), F("strength", P01)],
        "ringing-out tails after hits or section ends", id_kind="decay_tail"),
    # ---------------------------------------------------------------- structure
    _ev("sections", "structure", "segment", [
        F("id", idref("section")), F("t", T), F("d", D),
        F("label", string("intro, verse, pre-chorus, chorus, bridge, inst, solo, break, outro, silence (open vocabulary)",
                          pattern=r"^[a-z][a-z-]*$")),
        F("occurrence", integer("1-based count of this label so far", minimum=1)),
        F("occurrence_label", string("label#occurrence, e.g. chorus#2", pattern=r"^[a-z][a-z-]*#\d+$")),
        F("repeat_group", idref("repeat_group")), F("start_bar", integer(minimum=0)), F("n_bars", integer(minimum=1)),
        F("label_probs", mapof(P01, "label -> probability")), F("conf", P01), F("boundary_conf", P01),
    ], "CANONICAL sections; boundaries on downbeats; segments shorter than 2 bars are merged", id_kind="section"),
    _ev("phrases", "structure", "segment", [F("id", idref("phrase")), F("t", T), F("d", D), F("start_bar", integer(minimum=0)),
                                            F("n_bars", integer(minimum=1)), F("section_id", idref("section"))],
        "4/8/16-bar phrases aligned to section starts", id_kind="phrase"),
    _ev("edm_roles", "structure", "segment", [F("id", idref("edm_role")), F("t", T), F("d", D),
                                              F("role", string(enum=["build", "drop", "breakdown"])), F("start_bar", integer(minimum=0)),
                                              F("n_bars", integer(minimum=1)), F("section_id", idref("section")), F("conf", P01),
                                              F("evidence", arr(string()), required=False)],
        "THE definition of builds, drops and breakdowns (snapped to downbeats)", id_kind="edm_role"),
    # ---------------------------------------------------------------- stems
    _ev("stem_activity", "stem_activity", "segment", [F("t", T), F("d", D), F("stem", string(enum=STEM_ENUM)), F("mean_db", num("dBFS"))],
        "active segments per stem"),
    _ev("drum_hits", "drums", "event", [F("t", T), F("drum", string(enum=["kick", "snare", "hat", "tom", "cymbal", "perc"])),
                                        F("vel", P01), F("level_db", num("dBFS")), F("conf", P01),
                                        F("source", string(enum=["drumsep", "classifier"]))],
        "classified drum hits"),
    _ev("instruments", "instruments", "segment", [F("t", T), F("d", D), F("instrument", string("instrument slug", pattern=r"^[a-z0-9_]+$")),
                                                  F("conf", P01), F("evidence", string(enum=["stem", "tagger", "both"])),
                                                  F("stem", nullable(string(enum=STEM_ENUM)))],
        "instrument timeline segments"),
    _ev("vocal_style", "instruments", "segment", [F("t", T), F("d", D), F("style", string(enum=["singing", "speech", "rap"])), F("conf", P01)],
        "lead-vocal style segments"),
    _ev("notes.{src}", "notes", "event", _NOTE_FIELDS, "note events of one pitched stem (src = bass, piano, guitar, other)",
        schema="events/notes"),
    _ev("notes.vocals", "vocals", "event", _NOTE_FIELDS, "lead-vocal notes (from f0)", schema="events/notes"),
    _ev("vocal_phrases", "vocals", "segment", [F("id", idref("vocal_phrase")), F("t", T), F("d", D), F("median_midi", num("MIDI")),
                                               F("min_midi", num("MIDI")), F("max_midi", num("MIDI")), F("mean_db", num("dBFS"))],
        "voiced phrases of the lead vocal", id_kind="vocal_phrase"),
    _ev("mood", "mood", "segment", [F("t", T), F("d", D), F("section_id", idref("section")), F("valence", P01), F("arousal", P01),
                                    F("valence_conf", P01), F("arousal_conf", P01), F("tags", arr(string(), "top mood/theme tags"))],
        "mood per section"),
    # ---------------------------------------------------------------- words
    _ev("voice_spans", "voices", "segment", [F("t", T), F("d", D), F("line_id", idref("line")),
                                             F("first_word", nullable(idref("word"))), F("last_word", nullable(idref("word"))),
                                             F("voice_id", idref("voice")), F("conf", P01), F("review", boolean("low confidence: flagged for review"))],
        "proposed voice per line or word span (a line may have several spans)"),
    _ev("voice_activity", "voices", "segment", [F("t", T), F("d", D), F("voice_id", idref("voice"))], "when each voice sings"),
    _ev("visemes", "lipsync", "segment", [F("t", T), F("d", D), F("viseme", string(enum=list("ABCDEFGHX"))),
                                          F("voice_id", nullable(idref("voice"))), F("line_id", nullable(idref("line")))],
        "Rhubarb mouth shapes A-H, X (Preston Blair mapping in CONTRACT.md)", path="lipsync/visemes.json", required=False),
    _ev("phonemes", "lipsync", "segment", [F("t", T), F("d", D), F("phoneme", string("ARPAbet or IPA symbol")),
                                           F("voice_id", nullable(idref("voice"))), F("word_id", nullable(idref("word")))],
        "phonemes", path="lipsync/phonemes.json", required=False),
    # ---------------------------------------------------------------- choreo
    _ev("counts", "choreo", "segment", [
        F("id", idref("eight")), F("t", T), F("d", D),
        F("start_beat", integer("beat_index of the first count (may be < 0 for the E000 lead-in)")),
        F("len", integer("beats in this count: 8 (6 in 3/4), shorter when partial", minimum=1, maximum=8)),
        F("first_count", integer("1, or 5 for the E000 lead-in", minimum=1, maximum=8)),
        F("phrase_id", nullable(idref("phrase"))), F("section_id", nullable(idref("section"))),
        F("partial", boolean()), F("lead_in", boolean()), F("in_pulse", boolean()),
        F("accents", arr(P01, "accent per count (len entries)")),
    ], "eight-counts; restart at every phrase and section start; E000 = synthesised 5-6-7-8 lead-in", id_kind="eight"),
    _ev("grooves", "choreo", "segment", [
        F("t", T), F("d", D), F("bar", integer(minimum=0)), F("groove_id", idref("groove")),
        F("swing", num("ratio", "long/short 8th ratio; 1 = straight", minimum=0)), F("syncopation", P01),
        F("pattern", obj({k: arr(P01, f"16 steps of {k}", 16, 16) for k in ("kick", "snare", "hat", "perc")})),
    ], "per-bar 16-step groove matrix"),
    _ev("hit_points", "choreo", "event", [F("id", idref("hit_point")), F("t", T), F("strength", P01), F("rank", integer(minimum=1)),
                                          F("kinds", arr(string(), "what coincides: drum, onset, impact, stop, vocal_onset, chord, ...")),
                                          F("sources", arr(SOURCE_REF))],
        "ranked coinciding accents", id_kind="hit_point"),
    _ev("holds", "choreo", "segment", [F("id", idref("hold")), F("t", T), F("d", D),
                                       F("kind", string(enum=["vocal_note", "chord", "decay", "silence"])), F("strength", P01),
                                       F("source", SOURCE_REF)],
        "sustained moments to hold a pose", id_kind="hold"),
    # ---------------------------------------------------------------- cues
    _ev("cues", "cues", "event", [
        F("id", idref("cue")), F("t", T),
        F("kind", string(enum=["section", "drop", "build_start", "breakdown", "phrase", "impact", "stop", "silence", "hit_point",
                               "downbeat", "beat", "pinned"])),
        F("tier", integer("1 section/drop/build start, 2 phrase/impact/stop, 3 hit point/downbeat, 4 beat", minimum=1, maximum=4)),
        F("strength", nullable(P01)), F("lead_in_s", nullable(num("s", "recommended anticipation window", minimum=0))),
        F("next_major_in_s", nullable(num("s", "time to the next tier-1 cue", minimum=0))), F("source", SOURCE_REF),
        F("kinds", arr(string(), "every kind merged into this cue, highest priority first (kinds[0] == kind)", min_items=1), required=False),
        F("sources", arr(SOURCE_REF, "the source of every merged kind (sources[0] == source)", min_items=1), required=False),
    ], "THE list agents cut from; ONE cue per time (D37: co-timed cues merge, kinds[]/sources[] list them); tier-4 beats are references to events/beats.json: strength/lead_in_s null", id_kind="cue"),
    _ev("moments", "cues", "event", [F("rank", integer(minimum=1)), F("t", T), F("d", nullable(D)), F("cue_id", idref("cue")),
                                     F("kind", string()), F("strength", P01), F("description", string("no lyric text beyond 10 words"))],
        "top moments (the brief shows the top 15)"),
    # ---------------------------------------------------------------- meaning
    _ev("singing", "meaning", "segment", [F("t", T), F("d", D), F("character_id", idref("character")), F("voice_id", idref("voice")),
                                          F("line_id", idref("line")), F("lead_backing", string(enum=["lead", "backing"]))],
        "who sings when: lines joined with voices and characters (singerAt reads this)"),
]
EVENTS_BY_NAME = {e.name: e for e in EVENTS}


def event_def(name: str) -> EventDef:
    """Look up an events name, resolving notes.<src> families."""
    if name in EVENTS_BY_NAME:
        return EVENTS_BY_NAME[name]
    if name.startswith("notes.") and name[6:] in PITCHED_SOURCES:
        return EVENTS_BY_NAME["notes.{src}"]
    raise KeyError(name)


# ============================================================================ JSON files
PROVENANCE = obj({
    "stage": string(), "stage_version": SEMVER, "contract_version": SEMVER, "key": SHA,
    "params": obj(desc="resolved params (thread counts included)"),
    "models": arr(obj({"id": string(), "licence": string()}, opt={"revision": nullable(string())})),
    "tools": arr(obj({"name": string(), "version": string()})),
    "device": string("cpu | rocm | vulkan"), "upstream": mapof(SHA, "upstream stage -> cache key"),
    "overrides_applied": arr(obj({"key": string(), "value": {}})), "fallbacks": arr(string()),
}, opt={"notes": arr(string()), "confidence": nullable(P01)},
    desc="deterministic provenance (no timestamps or hosts: those go to run.json)")

EVENTS_ENVELOPE = obj({
    "schema": string("events schema id, e.g. mvh/events/beats", pattern=r"^mvh/events/"),
    "schema_version": SEMVER, "name": string(pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$"),
    "kind": string(enum=["event", "segment"]),
    "fields": mapof(obj({"unit": nullable(string()), "type": string()}, opt={"description": string()}), "field -> unit/type"),
    "provenance": ref("envelope/provenance"),
    "items": arr(obj({"t": num("s")}, opt={"d": D, "id": string()}), "sorted by t (ties: file order)"),
}, desc="event-file envelope")
EVENTS_ENVELOPE["allOf"] = [{"if": {"properties": {"kind": {"const": "segment"}}},
                             "then": {"properties": {"items": {"items": {"required": ["t", "d"]}}}}}]

MANIFEST = obj({
    "schema": {"const": "mvh/manifest"}, "schema_version": SEMVER, "mvh_version": string(), "contract_version": SEMVER,
    "slug": string(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$"),
    "source": obj({"file_name": string(), "pcm_sha256": SHA, "duration_s": num("s", minimum=0), "sample_rate": integer(minimum=1),
                   "channels": integer(minimum=1), "n_samples": integer(minimum=0)}),
    "timebase": obj({"unit": {"const": "s"}, "origin": string(), "soundtrack": string("audio/mix.flac (or audio/mix.wav when |x| > 1)"),
                     "curve_rate_hz": {"const": 100}, "frame_rule": {"const": "centred"}}),
    "status": obj({"stages": mapof(string(enum=["done", "degraded", "skipped", "failed", "pending", "stale"])),
                   "meaning": string(enum=["user", "draft", "pending"]), "lyrics_grade": nullable(GRADE),
                   "stems": boolean(), "visemes": boolean(), "flags": arr(string(), "low-confidence and QA flags")}),
    "summary": obj({
        "title": nullable(string()), "artist": nullable(string()), "duration_s": num("s"), "bpm": nullable(num("BPM")),
        "feel": nullable(string(enum=["normal", "half_time", "double_time"])), "meter": nullable(string("e.g. 4/4")),
        "key": nullable(string()), "integrated_lufs": nullable(num("LUFS")), "lra_lu": nullable(num("LU")),
        "true_peak_dbtp": nullable(num("dBTP")),
        "vocal_range": nullable(obj({"low": string("note name"), "high": string("note name")})),
        "instrumentation": arr(string(), max_items=16), "palette": arr(HEX, max_items=12),
    }, opt={"stages": mapof(obj(), "per-stage scalars (StageResult.summary)")}),
    "files": arr(obj({"path": string(), "kind": string(enum=["curve", "matrix", "events", "table", "audio", "midi", "text", "json"]),
                      "stage": string()}, opt={"events": string("events name when the path is not events/<name>.json")})),
    "warnings": arr(string()),
}, desc="manifest.json: index only, no data arrays, <= 3k tokens")

CURVES_INDEX = obj({
    "schema": {"const": "mvh/curves_index"}, "schema_version": SEMVER,
    "files": mapof(obj({"path": string(), "dtype": string(enum=["f32le", "u8"]), "layout": string(enum=["column-major", "row-major"]),
                        "rate_hz": num("Hz"), "n_frames": integer(minimum=0), "n_channels": integer(minimum=1)},
                       opt={"quant": obj({"scale": num(), "offset": num()}, desc="value = offset + scale * u8"),
                            "band_edges_hz": arr(num("Hz"), "129 edges for spectrum128")})),
    "channels": arr(obj({
        "id": string(pattern=r"^[a-z][a-z0-9_]*(\.[A-Za-z0-9_]+)+$|^spectrum128$"), "file": string(),
        "offset_bytes": integer(minimum=0), "n": integer(minimum=0), "rate_hz": num("Hz"), "unit": string(),
        "range": arr(num(), min_items=2, max_items=2), "resample": string(enum=["linear", "mean", "max", "hold"]),
        "norm": nullable(obj({"method": string()}, opt={"of": string(), "lo": num(), "hi": num()})),
        "special": nullable(obj(opt={"nan": string(enum=["unvoiced"]), "floor": num()})),
        "twin": nullable(string()), "stage": string(), "description": string(),
    })),
}, desc="curves/index.json: the curve channel registry for this song")

RUN = obj({
    "schema": {"const": "mvh/run"}, "schema_version": SEMVER, "mvh_version": string(), "contract_version": SEMVER,
    "started": string("ISO 8601"), "finished": nullable(string()), "profile": string(enum=["max", "draft"]),
    "host": obj({"os": string(), "cpu": string(), "threads": integer(minimum=1)}, opt={"ram_gb": num()}),
    "device": obj({"class": string(), "gpu": nullable(string())}),
    "versions": obj({"python": string(), "ffmpeg": obj({"version": string(), "buildconf": arr(string())}),
                     "packages": mapof(string())}),
    "stages": mapof(obj({"status": string(enum=["done", "degraded", "skipped", "failed", "pending", "stale"]),
                         "cache": string(enum=["hit", "miss", "forced"]), "key": nullable(SHA), "seconds": nullable(num("s")),
                         "threads": integer(minimum=1), "device": string(), "env": string(enum=["main", "sep"]),
                         "variant": nullable(string()), "fallbacks": arr(string()), "warnings": arr(string())})),
    "licences": arr(obj({"model_id": string(), "licence": string(), "used_by": arr(string())})),
    "fallbacks_used": arr(string()), "warnings": arr(string()),
}, desc="run.json: everything volatile (never compared for determinism)")

MODELS_LOCK = obj({
    "models": arr(obj({"id": string(pattern=r"^[a-z0-9][a-z0-9_.-]*$"),
                       # env labels as written by W0 (scripts/fetch_models.py + envs/sep/models.fragment.json): the sep
                       # worker's two venvs are sep-rocm / sep-cpu, ggml files are read by ffmpeg's whisper filter
                       "envs": arr(string(enum=["main", "sep", "sep-rocm", "sep-cpu", "ffmpeg-whisper"]), min_items=1),
                       "files": arr(obj({"path": string(), "url": string(pattern=r"^https://"), "revision": nullable(string()),
                                         "sha256": SHA, "size": integer(minimum=0)}), min_items=1),
                       "licence": string(), "used_by": arr(string())},
                      opt={"bundled": boolean("the file ships inside a wheel (verified, never downloaded)"),
                           "note": string(), "notes": string(), "source": string()})),
}, opt={"schema_version": SEMVER, "schema": integer("lock format version (W0 writes 1)", minimum=1),
        "generated_by": string(), "models_dir": string("models root, e.g. %LOCALAPPDATA%\\mvh\\models")},
    desc="models.lock.json (repo root): the only list of downloadable model files")

OVERRIDES = obj(opt={
    "schema": {"const": "mvh/overrides"}, "schema_version": SEMVER,
    "rhythm": obj(opt={"beat_offset_s": num("s", "shift of the whole beat grid"), "bpm": num("BPM", "forced global tempo", minimum=1),
                       "downbeat_phase": integer("beats to rotate the bar numbering by")}),
    "structure": obj(opt={"boundaries": arr(obj({"t": num("s"), "action": string(enum=["add", "remove", "move"])},
                                                opt={"to_t": num("s")}), "edits anchored by time"),
                          "labels": arr(obj({"t": num("s", "any time inside the section"), "label": string(pattern=r"^[a-z][a-z-]*$")}))}),
    "lyrics": obj(opt={"lines": mapof(obj({"dt": num("s")}), "line id -> nudge", keys=ID_KINDS["line"].regex),
                       "words": mapof(obj(opt={"t": num("s"), "d": D, "dt": num("s")}), "word id -> timing", keys=ID_KINDS["word"].regex)}),
    "voices": obj(opt={"lines": mapof(idref("voice"), "line id -> voice id", keys=ID_KINDS["line"].regex)}),
    "cues": obj(opt={"pinned": arr(obj({"t": num("s")}, opt={"d": D, "note": string()}))}),
}, desc="overrides.json: user corrections (viewer edit mode or by hand); keys map to StageSpec.override_keys")
OVERRIDE_KEYS = {
    "rhythm.beat_offset_s": "rhythm", "rhythm.bpm": "rhythm", "rhythm.downbeat_phase": "rhythm",
    "structure.boundaries": "structure", "structure.labels": "structure",
    "lyrics.lines": "lyrics", "lyrics.words": "lyrics", "voices.lines": "voices", "cues.pinned": "cues",
}

STAGE_RESULT = obj({
    "schema": {"const": "mvh/stage_result"}, "stage": string(), "stage_version": SEMVER,
    "status": string(enum=["ok", "degraded", "skipped", "failed"]),
    "outputs": arr(obj({"path": string(), "kind": string(), "sha256": SHA, "bytes": integer(minimum=0)})),
    "summary": obj(), "warnings": arr(string()), "fallbacks": arr(string()),
}, opt={"confidence": nullable(P01), "provenance": obj()}, desc="result.json written by a stage run (and by the sep worker)")

# ---------------------------------------------------------------- per-file schemas
NOTE_STATS = obj({"midi": integer(minimum=0, maximum=127), "name": string(), "hz": num("Hz"), "t": T})
FILE_SCHEMAS: dict[str, dict] = {
    "files/source": obj({
        "file_name": string(), "codec": string(), "sample_rate": integer(minimum=1), "channels": integer(minimum=1),
        "n_samples": integer(minimum=0), "duration_s": num("s"), "pcm_sha256": SHA, "lossless": boolean(),
        "peak_abs": num("linear", "max |x| of the canonical decode"), "decode_warnings": integer(minimum=0),
        "tags": mapof(string(), "ffprobe tags, keys lower-cased"), "has_cover": boolean(), "palette": arr(HEX, max_items=12),
        "soundtrack": string("audio/mix.flac, or audio/mix.wav when peak_abs > 1"),
    }),
    "files/identity": obj({
        "title": nullable(string()), "artist": nullable(string()), "album": nullable(string()), "duration_s": num("s"),
        "source": string(enum=["tags", "acoustid", "musicbrainz", "user"]), "conf": P01,
        "credits": arr(obj({"role": string(), "name": string()})),
    }, opt={"album_artist": nullable(string()), "year": nullable(integer()), "isrc": nullable(string()), "track_no": nullable(integer()),
            "genre": nullable(string()), "mb_recording_id": nullable(string()), "mb_artist_ids": arr(string()),
            "acoustid_id": nullable(string()), "acoustid_score": nullable(P01)}),
    "files/separation": obj({
        "variant": string(enum=["rocm", "cpu", "htdemucs", "fast"]), "degraded": boolean(), "lead_backing_split": boolean(),
        "stems": mapof(obj({"model": string(), "file": string()})), "models": arr(obj({"id": string(), "licence": string()})),
    }, opt={"invariants": obj(opt={"sum_error_db": num("dB"), "gain_db": mapof(num("dB"))})}),
    "files/stems": obj({
        "stems": mapof(obj({"present": boolean(), "active_ratio": P01, "median_rms_db": num("dBFS"), "peak_db": num("dBFS"),
                            "share_of_mix_db": num("dB")}), keys=r"^[a-z_]+$"),
        "thresholds": obj({"active_db": num("dBFS"), "within_db": num("dB"), "attack_ms": num("ms"), "release_ms": num("ms")}),
    }),
    "files/loudness": obj({
        "integrated_lufs": num("LUFS"), "lra_lu": num("LU"), "lra_low_lufs": num("LUFS"), "lra_high_lufs": num("LUFS"),
        "true_peak_dbtp": num("dBTP"), "sample_peak_db": num("dBFS"), "plr_db": num("dB"),
    }, opt={"ebur128": obj(opt={"integrated_lufs": num("LUFS"), "lra_lu": num("LU"), "true_peak_dbtp": num("dBTP"), "diff_lu": num("LU")}),
            "clipped_samples": integer(minimum=0), "curve_offsets_s": obj(opt={"momentary": num("s"), "short_term": num("s")})}),
    "files/tempo": obj({
        "bpm": num("BPM"), "confidence": P01, "feel": string(enum=["normal", "half_time", "double_time"]), "is_variable": boolean(),
        "candidates": arr(obj({"bpm": num("BPM"), "score": num(), "relation": string("x1, x2, x0.5, x1.5, x0.667, x1.333, x0.75")})),
        "meter": obj({"time_signature": string(pattern=r"^\d+/\d+$"), "beats_per_bar": integer(minimum=1), "confidence": P01,
                      "changes": arr(obj({"t": T, "bar": integer(minimum=0), "beats_per_bar": integer(minimum=1)}))}),
        "qa": obj({"beat_agreement_f": nullable(P01), "downbeat_agreement_f": nullable(P01), "flags": arr(string())}),
    }, opt={"estimates": mapof(nullable(num("BPM"))), "agreement": string()}),
    "files/key": obj({
        "global": obj({"key": string(), "tonic_pc": PC, "mode": string(enum=["major", "minor"]), "conf": P01}),
        "agreement": string("agree | relative | parallel | fifth | disagree"), "flags": arr(string()),
    }, opt={"methods": mapof(obj())}),
    "files/structure": obj({
        "repeat_groups": mapof(obj({"label": string(), "section_ids": arr(idref("section")), "similarity": P01}),
                               keys=ID_KINDS["repeat_group"].regex),
        "phrase_bars": integer("dominant phrase length in bars (4, 8 or 16)", minimum=1), "n_sections": integer(minimum=0),
    }),
    "files/instruments": obj({
        "summary": arr(obj({"instrument": string(), "coverage": P01, "mean_conf": P01})), "vocabulary": arr(string()),
        "vocal_style": obj({"dominant": string(enum=["singing", "speech", "rap", "none"]),
                            "shares": obj({"singing": P01, "speech": P01, "rap": P01})}),
    }, opt={"top_tags": arr(obj({"label": string(), "p": P01}))}),
    "files/notes_index": obj({
        "sources": mapof(obj({"events": string(), "midi": nullable(string()), "count": integer(minimum=0),
                              "lowest": nullable(integer(minimum=0, maximum=127)), "highest": nullable(integer(minimum=0, maximum=127)),
                              "pc_histogram": arr(num(minimum=0), min_items=12, max_items=12), "density_per_s": num("notes/s")})),
        "tempo_map": string("how notes.mid's tempo map was built"),
    }),
    "files/vocal_range": obj({
        "present": boolean("false when < ~8 voiced seconds; then the statistics are null"), "voiced_s": num("s"),
        "lowest": nullable(NOTE_STATS), "highest": nullable(NOTE_STATS),
        "p2": nullable(num("MIDI")), "p98": nullable(num("MIDI")), "p10": nullable(num("MIDI")), "p90": nullable(num("MIDI")),
        "median_midi": nullable(num("MIDI")), "span_semitones": nullable(num("semitones")),
        "register": nullable(string("bass, baritone, tenor, alto, mezzo, soprano (low confidence)")), "conf": P01,
    }),
    "files/mood": obj({"global": obj({"valence": P01, "arousal": P01, "valence_conf": P01, "arousal_conf": P01,
                                      "tags": arr(obj({"tag": string(), "p": P01}))})}, opt={"models": arr(string())}),
    "files/voices": obj({
        "n_voices": integer(minimum=0), "method": string(), "n_source": string(enum=["intent", "estimate", "hints"]),
        "voices": arr(obj({"id": idref("voice"), "seconds": num("s"), "n_lines": integer(minimum=0),
                           "proposed_character_id": nullable(idref("character")), "hint": nullable(string("speaker label from the lyrics source"))})),
    }),
    "files/grooves": obj({"grooves": arr(obj({
        "id": idref("groove"), "n_bars": integer(minimum=1), "bars": arr(integer(minimum=0)), "swing": num("ratio"), "syncopation": P01,
        "prototype": obj({k: arr(P01, min_items=16, max_items=16) for k in ("kick", "snare", "hat", "perc")})}))}),
    "files/lyrics": obj({
        "schema": {"const": "mvh/files/lyrics"}, "schema_version": SEMVER, "provenance": ref("envelope/provenance"),
        "source": obj({"kind": string(enum=["user", "embedded", "lrclib", "transcribed", "none"]), "lrclib_id": nullable(integer()),
                       "duration_diff_s": nullable(num("s")), "has_word_sync": boolean()}),
        "instrumental": boolean(), "language": nullable(string()), "grade": nullable(GRADE),
        "lyrics_match_score": nullable(P01), "coverage": P01,
        "lines": arr(obj({
            "id": idref("line"), "t": T, "d": D, "text": string("lyric text (stays local; never logged)"),
            "section_id": nullable(idref("section")), "text_group": idref("text_group"), "repeat_group": nullable(idref("line_group")),
            "conf": P01, "grade": GRADE, "first_word": nullable(idref("word")), "n_words": integer(minimum=0),
            "backing": boolean("parenthetical / backing line"), "speaker_hint": nullable(string("speaker label from the source")),
            "timing_source": string(enum=["user", "lrclib_word", "lrclib_line", "ctc", "whisper", "stable_ts", "interpolated"]),
        })),
        "words": arr(obj({"id": idref("word"), "line_id": idref("line"), "t": T, "d": D, "text": string(), "conf": P01},
                         opt={"flags": arr(string())})),
    }),
    "files/meaning": obj({
        "schema": {"const": "mvh/files/meaning"}, "schema_version": SEMVER,
        "status": string(enum=["user", "draft", "pending"]),
        "logline": nullable(string()), "summary": nullable(string()), "themes": arr(CLAIM),
        "perspective": obj({"narrator": nullable(string()), "addressee": nullable(string())}),
        "characters": arr(obj({"id": idref("character"), "name": string(), "description": nullable(string()),
                               "voice_ids": arr(idref("voice")), "lead_backing": nullable(string(enum=["lead", "backing", "both"])),
                               "line_ids": arr(idref("line")), "section_ids": arr(idref("section")), "provenance": CLAIM_PROV})),
        "setting": nullable(string()),
        "motifs": arr(obj({"id": idref("motif"), "name": string(),
                           "occurrences": arr(obj({"t": T}, opt={"d": D, "line_id": idref("line")})), "provenance": CLAIM_PROV})),
        "symbolism": arr(CLAIM),
        "sections": arr(obj({
            "section_id": idref("section"), "t0": T, "t1": T, "occurrence_label": string(),
            "feel": nullable(string()), "meaning": nullable(string()),
            "emotion": obj({"lyric": nullable(string()), "audio": nullable(string()), "agree": nullable(boolean())}),
            "palette_hint": arr(HEX), "movement_hint": nullable(string()), "camera_hint": nullable(string()),
            "characters_present": arr(idref("character")), "do_not": arr(string()), "provenance": CLAIM_PROV,
        })),
        "palette": arr(HEX), "tone": nullable(string()), "do_not": arr(string("the user's words, verbatim")),
        "open_questions": arr(string()),
    }, opt={"provenance": ref("envelope/provenance")}),
    "files/meaning_input": obj({"schema_version": SEMVER, "song": obj({"title": nullable(string()), "artist": nullable(string()),
                                                                     "duration_s": num("s")}),
                                "sections": arr(obj({"id": idref("section"), "t": T, "d": D, "label": string()})),
                                "facts": obj(desc="facts the draft may cite"),
                                "lines_file": nullable(string("lyrics/lines.tsv, or null with --no-lyrics-to-agents"))}),
    "files/orphans": obj({"orphans": arr(obj({"old_section_id": idref("section"), "t_range": arr(T, min_items=2, max_items=2),
                                              "occurrence_label": nullable(string()), "claim": obj(), "reason": string()}))}),
    "intermediate/allin1": obj({
        "bpm": nullable(num("BPM")), "beats": arr(T), "downbeats": arr(T), "beat_positions": arr(integer(minimum=1)),
        "segments": arr(obj({"start": T, "end": T, "label": string()})), "labels": arr(string("activation label order")),
        "activations": obj({"file": string(), "rate_hz": num("Hz"), "columns": arr(string()), "frames": integer(minimum=0)},
                           desc="row-major float32 [frames x columns]: beat, downbeat, boundary, then label probabilities"),
        "embeddings": nullable(obj({"file": string(), "rate_hz": num("Hz"), "dim": integer(minimum=1), "frames": integer(minimum=0)})),
    }),
}

# ---------------------------------------------------------------- tables
@dataclass(frozen=True)
class TableDef:
    path: str
    stage: str
    columns: tuple[Field, ...]
    description: str
    sep: str = ","
    schema: str = ""


def _tbl(path, stage, cols, desc, sep=",", schema=""):
    return TableDef(path, stage, tuple(cols), desc, sep, schema)


TABLES: list[TableDef] = [
    _tbl("tables/beats.csv", "choreo", [
        F("beat_index", integer(minimum=0)), F("t", T), F("bar", integer(minimum=0)), F("beat_in_bar", integer(minimum=1)),
        F("beats_in_bar", integer(minimum=1)), F("in_pulse", boolean()), F("strength", P01), F("section_id", nullable(idref("section"))),
        F("phrase_id", nullable(idref("phrase"))), F("eight_id", nullable(idref("eight"))), F("count", nullable(integer(minimum=1, maximum=8))),
        F("accent", P01)], "one row per beat (from events/beats.json, joined with sections, phrases and counts)", schema="tables/beats"),
    _tbl("tables/bars.csv", "choreo", [
        F("bar", integer(minimum=0)), F("t", T), F("d", D), F("beats_in_bar", integer(minimum=1)), F("n_beats", integer(minimum=1)),
        F("pickup", boolean()), F("in_pulse", boolean()), F("section_id", nullable(idref("section"))), F("phrase_id", nullable(idref("phrase"))),
        F("groove_id", nullable(idref("groove"))), F("swing", nullable(num("ratio"))), F("syncopation", nullable(P01))],
        "one row per bar (from events/bars.json, joined with sections, phrases and grooves)", schema="tables/bars"),
    _tbl("tables/sections.csv", "choreo", [
        F("id", idref("section")), F("t", T), F("d", D), F("label", string()), F("occurrence", integer(minimum=1)),
        F("repeat_group", idref("repeat_group")), F("start_bar", integer(minimum=0)), F("n_bars", integer(minimum=1)),
        F("edm_role", nullable(string(enum=["build", "drop", "breakdown"]))),
        F("level", nullable(string(enum=["silence", "quiet", "soft", "medium", "loud", "peak"]))), F("mean_lufs", nullable(num("LUFS")))],
        "one row per section (from events/sections.json)", schema="tables/sections"),
    _tbl("lyrics/lines.tsv", "meaning", [
        F("id", idref("line")), F("t", T), F("d", D), F("section_id", nullable(idref("section"))),
        F("singer", nullable(string("every character singing the line, lead first, joined with + (C1+C2)", pattern=r"^C[1-9]\d*(\+C[1-9]\d*)*$"))),
        F("repeat_group", nullable(idref("line_group"))), F("grade", GRADE),
        F("text", string("tabs and newlines replaced by spaces"))],
        "lyric lines, safe for an agent's context (PLAN §4.1 column order)", sep="\t", schema="tables/lines"),
    _tbl("frames/{fps}fps.csv", "frames", [F("frame", integer()), F("t", T)],
         "mvh frames: one row per video frame (frame, t = time_of(frame), then one column per requested channel)", schema="tables/frames"),
]
TABLES_BY_PATH = {t.path: t for t in TABLES}


# ============================================================================ files per stage
@dataclass(frozen=True)
class FileDef:
    path: str
    stage: str
    kind: str
    schema: str | None
    description: str
    required: bool = True
    public: bool = True
    events: str | None = None
    channels: tuple[str, ...] = ()


def _f(path, stage, kind, schema, desc, **kw) -> FileDef:
    return FileDef(path, stage, kind, schema, desc, **kw)


_STEMS = [_f(f"stems/{s}.flac", "separate_hq", "audio", None,
             f"{s} stem, sample-aligned with the mix, same length (24-bit; plus stems/{s}.wav float when |x| > 1)")
          for s in STEM_NAMES]
_DRUMSUB = [_f(f"stems/drums/{s}.flac", "separate_hq", "audio", None, f"drum sub-stem {s} (DrumSep; Should)", required=False)
            for s in DRUM_SUBSTEMS]

FILES: list[FileDef] = [
    # ingest
    _f("audio/mix.flac", "ingest", "audio", None, "THE soundtrack and timebase: 24-bit FLAC of the canonical decode"),
    _f("audio/mix.wav", "ingest", "audio", None, "float32 WAV twin, written only when the decode exceeds full scale", required=False),
    _f("audio/preview.opus", "ingest", "audio", None, "preview for the viewer"),
    _f("artwork/cover.jpg", "ingest", "audio", None, "embedded cover art (absent when the file has none)", required=False),
    _f("meta/source.json", "ingest", "json", "files/source", "decode facts, raw tags, palette"),
    _f("canonical.wav", "ingest", "audio", None, "canonical float32 WAV at the native rate (cache only; read via ctx.audio('mix'))",
       public=False),
    # identity
    _f("meta/identity.json", "identity", "json", "files/identity", "title, artist, album, credits, MusicBrainz/AcoustID ids"),
    # separation
    _f("fast/{stem}.wav", "separate_fast", "audio", None,
       "htdemucs stems (vocals, drums, bass, other; + guitar, piano in draft), float32 (cache only; ctx.audio('fast:<stem>'))",
       public=False),
    _f("fast/separation.json", "separate_fast", "json", "files/separation", "separate_fast model facts (cache only)", public=False),
    *_STEMS, *_DRUMSUB,
    _f("meta/separation.json", "separate_hq", "json", "files/separation", "separator variant, models, lead/backing split, invariants"),
    # allin1
    _f("allin1.json", "allin1", "json", "intermediate/allin1", "all-in-one beats, downbeats, segments (cache only)", public=False),
    _f("activations.f32", "allin1", "matrix", None, "row-major float32 activations at 100 Hz (cache only)", public=False,
       channels=("allin1.activations",)),
    _f("embeddings.f32", "allin1", "matrix", None, "row-major float32 embeddings (cache only)", public=False, required=False,
       channels=("allin1.embeddings",)),
    # loudness / rhythm / harmony / structure / stems / instruments / notes / vocals / mood / voices / choreo
    _f("meta/loudness.json", "loudness", "json", "files/loudness", "integrated loudness, LRA, true peak, PLR"),
    _f("meta/tempo.json", "rhythm", "json", "files/tempo", "tempo, alternatives, feel, meter, rhythm QA"),
    _f("meta/key.json", "harmony", "json", "files/key", "global key and method agreement"),
    _f("meta/structure.json", "structure", "json", "files/structure", "repeat groups and phrase length"),
    _f("meta/stems.json", "stem_activity", "json", "files/stems", "per-stem presence and level statistics"),
    _f("meta/instruments.json", "instruments", "json", "files/instruments", "instrument summary and vocal style"),
    _f("notes/notes.json", "notes", "json", "files/notes_index", "per-source note statistics and file index"),
    _f("notes/notes.mid", "notes", "midi", None, "one track per source (bass, piano, guitar, other); tempo map from the beat grid"),
    _f("notes/{src}.mid", "notes", "midi", None, "one MIDI file per source", required=False),
    _f("notes/vocals.mid", "vocals", "midi", None, "lead-vocal notes as MIDI (tempo map from the beat grid)"),
    _f("meta/vocal_range.json", "vocals", "json", "files/vocal_range", "vocal range, tessitura, register"),
    _f("meta/mood.json", "mood", "json", "files/mood", "global mood"),
    _f("meta/voices.json", "voices", "json", "files/voices", "voice clusters V1..Vn"),
    _f("meta/grooves.json", "choreo", "json", "files/grooves", "groove clusters G01.."),
    # lyrics
    _f("lyrics/lyrics.json", "lyrics", "json", "files/lyrics", "CANONICAL lyrics: lines and words with timing and confidence"),
    _f("lyrics/lyrics.lrc", "lyrics", "text", None, "LRC with A2 word tags"),
    _f("lyrics/lyrics.vtt", "lyrics", "text", None, "WebVTT with inline word timestamps"),
    _f("lyrics/lyrics.srt", "lyrics", "text", None, "SRT (line level)"),
    _f("lyrics/lyrics.ass", "lyrics", "text", None, "ASS karaoke (\\k tags)"),
    # meaning
    _f("meaning/interview.md", "meaning", "text", None, "questions for the user, generated from the facts"),
    _f("meaning/request.md", "meaning", "text", None, "instructions for the drafting agent"),
    _f("meaning/input.json", "meaning", "json", "files/meaning_input", "facts bundle for the drafting agent"),
    _f("meaning/schema.json", "meaning", "json", None, "JSON Schema the draft must satisfy (copy of mvh/files/meaning)"),
    _f("meaning/meaning.json", "meaning", "json", "files/meaning", "MERGED meaning (user > lyric > audio > external > speculative)"),
    _f("meaning/meaning.md", "meaning", "text", None, "human-readable meaning"),
    _f("meaning/orphans.json", "meaning", "json", "files/orphans", "claims that lost their section after a re-anchor"),
    # brief / viewer / frames
    _f("brief.md", "brief", "text", None, "the LLM entry point (<= 4k tokens)"),
    _f("viewer.html", "viewer", "text", None, "the viewer (file:// read-only with inlined preview data; mvh view for edit mode)"),
]

#: written by the runner's finalize step / the user, not by a stage
RUNNER_FILES: list[FileDef] = [
    _f("manifest.json", "_runner", "json", "envelope/manifest", "index only"),
    _f("curves/index.json", "_runner", "json", "envelope/curves_index", "curve registry with byte offsets"),
    *[_f(cf.path, "_runner", "matrix" if cf.layout == "row-major" else "curve", None, cf.description) for cf in CURVE_FILES.values()],
    _f("run.json", "_runner", "json", "envelope/run", "volatile run facts"),
    _f("lib/mvh.js", "_runner", "text", None, "JS loader (ES module, no dependencies)"),
    _f("lib/mvh_load.py", "_runner", "text", None, "Python loader (numpy only)"),
    _f("lib/mvh.glsl", "_runner", "text", None, "GLSL sampler mvhCurve"),
    _f("schema/{name}.schema.json", "_runner", "json", None, "copies of the contract schemas"),
    _f("overrides.json", "_user", "json", "envelope/overrides", "user corrections (viewer edit mode or by hand)", required=False),
    _f("meaning/intent.md", "_user", "text", None, "the user's answers (free text or the YAML template); never overwritten", required=False),
    _f("meaning/authored.json", "_user", "json", "files/meaning",
       "a meaning draft written by an agent or LLM (status draft); an input, never overwritten", required=False),
]

ENVELOPE_SCHEMAS = {
    "envelope/manifest": MANIFEST, "envelope/curves_index": CURVES_INDEX, "envelope/events": EVENTS_ENVELOPE,
    "envelope/provenance": PROVENANCE, "envelope/run": RUN, "envelope/models_lock": MODELS_LOCK,
    "envelope/overrides": OVERRIDES, "envelope/stage_result": STAGE_RESULT,
}


# ============================================================================ consumed-by
#: stage -> [(target, fields)]. Targets: 'events:<name>', 'file:<path>', 'table:<path>', 'curve:<id>',
#: 'matrix:<file id>', 'audio:mix' (every stage may read it), 'audio:<stem>' (stems/<stem>), 'audio:fast:<stem>',
#: 'intermediate:<stage>/<path>', 'ext:<path>' (external input). Every field listed here is FROZEN.
CONSUMES: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "ingest": [("ext:param:input", ())],
    "identity": [("file:meta/source.json", ("tags", "duration_s", "file_name")), ("audio:mix", ())],
    "separate_fast": [("audio:mix", ())],
    "separate_hq": [("audio:mix", ())],
    "allin1": [("audio:fast:{stem}", ()), ("intermediate:separate_fast/fast/separation.json", ("stems",))],
    "spectral": [("audio:mix", ())],
    "loudness": [("audio:mix", ())],
    "rhythm": [("audio:mix", ()),
               ("intermediate:allin1/allin1.json", ("bpm", "beats", "downbeats", "beat_positions")),
               ("intermediate:allin1/activations.f32", ()),
               ("events:hits.kick", ("t", "strength")), ("events:onsets.bass", ("t", "strength")),
               ("curve:flux.bass", ()), ("curve:hits.kick_raw", ())],
    "harmony": [("audio:mix", ()), ("events:beats", ("t", "beat_index", "in_pulse")), ("events:bars", ("t", "bar"))],
    "dynamics": [("curve:loud.short_term_lufs", ()), ("curve:loud.momentary_lufs", ()),
                 ("file:meta/loudness.json", ("integrated_lufs",)),
                 ("curve:bands.bass_db", ()), ("curve:bands.kick_db", ()), ("curve:timbre.centroid_hz", ()),
                 ("curve:timbre.slope_db_oct", ()), ("curve:stereo.width", ()), ("events:hits.kick", ("t", "strength")),
                 ("events:onsets.mid", ("t",)), ("events:onsets.high", ("t",)), ("events:bars", ("t", "bar", "d"))],
    "structure": [("intermediate:allin1/allin1.json", ("segments", "labels")), ("intermediate:allin1/activations.f32", ()),
                  ("intermediate:allin1/embeddings.f32", ()),
                  ("events:bars", ("t", "d", "bar", "beats_in_bar")), ("events:beats", ("t", "beat_index")),
                  ("curve:chroma.{pc}", ()), ("events:dynamics", ("t", "d", "level", "rel_lu")), ("curve:dyn.intensity", ()),
                  ("curve:dyn.novelty", ()), ("events:impacts", ("id", "t", "strength")), ("events:silences", ("id", "t", "d"))],
    "stem_activity": [("audio:mix", ()), ("audio:fast:{stem}", ()), ("audio:{stem}", ()),
                      ("file:meta/separation.json", ("stems", "lead_backing_split"))],
    "drums": [("audio:drums", ()), ("audio:drums_{sub}", ()), ("curve:stem.drums.active", ()),
              ("file:meta/stems.json", ("stems",))],
    "instruments": [("audio:mix", ()), ("audio:{stem}", ()), ("audio:fast:{stem}", ()), ("curve:stem.{stem}.active", ()),
                    ("file:meta/stems.json", ("stems",))],
    "notes": [("audio:{stem}", ()), ("curve:stem.{stem}.active", ()), ("file:meta/stems.json", ("stems",)),
              ("events:beats", ("t", "beat_index", "bar", "beat_in_bar")), ("events:bars", ("t", "bar", "beats_in_bar")),
              ("file:meta/tempo.json", ("bpm", "meter"))],
    "vocals": [("audio:lead_vocals", ()), ("curve:stem.lead_vocals.active", ()), ("file:meta/stems.json", ("stems",)),
               ("events:vocal_style", ("t", "d", "style")), ("events:beats", ("t", "beat_index")),
               ("file:meta/tempo.json", ("bpm",))],
    "mood": [("audio:mix", ()), ("events:sections", ("id", "t", "d"))],
    "lyrics": [("file:meta/identity.json", ("title", "artist", "album", "duration_s")), ("audio:lead_vocals", ()),
               ("curve:stem.lead_vocals.active", ()), ("events:sections", ("id", "t", "d", "repeat_group")),
               ("ext:param:lyrics", ()), ("ext:http:lrclib", ())],
    "voices": [("file:lyrics/lyrics.json", ("lines", "words", "source")), ("audio:vocals", ()), ("audio:lead_vocals", ()),
               ("audio:backing_vocals", ()), ("curve:stem.vocals.active", ()), ("ext:meaning/intent.md", ())],
    "lipsync": [("file:lyrics/lyrics.json", ("lines", "words")), ("events:voice_spans", ("t", "d", "line_id", "voice_id")),
                ("file:meta/voices.json", ("voices",)), ("audio:lead_vocals", ()), ("audio:vocals", ())],
    "choreo": [("events:beats", ("t", "beat_index", "bar", "beat_in_bar", "beats_in_bar", "in_pulse", "strength")),
               ("events:bars", ("t", "d", "bar", "beats_in_bar", "n_beats", "first_beat", "pickup")),
               ("file:meta/tempo.json", ("bpm", "meter")),
               ("events:sections", ("id", "t", "d", "start_bar", "n_bars", "label", "occurrence", "repeat_group")),
               ("events:phrases", ("id", "t", "d", "start_bar", "n_bars", "section_id")),
               ("events:edm_roles", ("id", "t", "d", "role")),
               ("events:drum_hits", ("t", "drum", "vel")), ("curve:drums.{drum}", ()),
               ("events:onsets.bass", ("t", "strength")), ("events:onsets.mid", ("t", "strength")), ("events:onsets.high", ("t", "strength")),
               ("events:hits.kick", ("t", "strength")),
               ("events:notes.vocals", ("t", "d", "midi")), ("events:vocal_phrases", ("id", "t", "d")), ("curve:vocal.voiced", ()),
               ("events:chords", ("t", "d", "label")),
               ("events:dynamics", ("t", "d", "level", "mean_lufs")), ("events:impacts", ("id", "t", "strength")),
               ("events:stops", ("id", "t", "strength")), ("events:silences", ("id", "t", "d")),
               ("events:decay_tails", ("id", "t", "d", "strength"))],
    "cues": [("events:counts", ("id", "t", "len")), ("events:hit_points", ("id", "t", "strength", "rank")),
             ("events:holds", ("id", "t", "d")),
             ("events:sections", ("id", "t", "d", "label")), ("events:phrases", ("id", "t", "d")),
             ("events:edm_roles", ("id", "t", "d", "role", "n_bars")),
             ("events:impacts", ("id", "t", "strength")), ("events:stops", ("id", "t", "strength")),
             ("events:silences", ("id", "t", "d")),
             ("events:beats", ("t", "beat_index", "beat_in_bar")), ("events:bars", ("t", "d", "bar")),
             ("events:drum_hits", ("t", "drum", "vel")), ("ext:overrides.json#cues.pinned", ())],
    "meaning": [("file:meta/identity.json", ("title", "artist", "album", "credits", "duration_s")),
                ("file:lyrics/lyrics.json", ("lines", "words", "grade", "instrumental", "language")),
                ("events:voice_spans", ("t", "d", "line_id", "voice_id", "conf", "review")),
                ("file:meta/voices.json", ("voices", "n_voices")),
                ("events:sections", ("id", "t", "d", "label", "occurrence", "occurrence_label", "repeat_group")),
                ("events:mood", ("section_id", "valence", "arousal", "tags")), ("file:meta/mood.json", ("global",)),
                ("file:meta/vocal_range.json", ("present", "lowest", "highest", "register")),
                ("file:meta/instruments.json", ("summary", "vocal_style")),
                ("events:moments", ("rank", "t", "cue_id", "kind")), ("events:cues", ("id", "t", "kind", "tier")),
                ("ext:meaning/intent.md", ()), ("ext:meaning/authored.json", ())],
    "brief": [("file:meta/source.json", ("duration_s", "palette")), ("file:meta/identity.json", ("title", "artist", "album")),
              ("file:meta/tempo.json", ("bpm", "feel", "meter", "confidence", "qa")), ("file:meta/key.json", ("global",)),
              ("file:meta/loudness.json", ("integrated_lufs", "lra_lu", "true_peak_dbtp")),
              ("file:meta/vocal_range.json", ("present", "lowest", "highest", "p10", "p90", "register")),
              ("file:meta/instruments.json", ("summary",)), ("file:meta/separation.json", ("degraded", "lead_backing_split")),
              ("file:meta/stems.json", ("stems",)),
              ("file:meaning/meaning.json", ("status", "logline", "characters", "do_not", "palette", "sections")),
              ("file:lyrics/lyrics.json", ("grade", "lines")),
              ("events:sections", ("id", "t", "d", "label", "occurrence_label", "repeat_group", "start_bar", "n_bars")),
              ("events:dynamics", ("t", "d", "level", "mean_lufs")), ("events:instruments", ("t", "d", "instrument")),
              ("events:vocal_phrases", ("t", "d", "min_midi", "max_midi")), ("events:hit_points", ("id", "t", "strength", "rank")),
              ("events:mood", ("section_id", "valence", "arousal", "tags")), ("events:edm_roles", ("id", "t", "d", "role")),
              ("events:counts", ("id", "t", "section_id", "len", "partial")), ("events:grooves", ("bar", "groove_id")),
              ("events:holds", ("id", "t", "d", "kind")), ("events:moments", ("rank", "t", "cue_id", "kind", "description")),
              ("events:cues", ("id", "t", "kind", "tier")), ("events:singing", ("t", "d", "character_id", "voice_id")),
              ("file:meta/voices.json", ("voices",)), ("file:meaning/orphans.json", ("orphans",)), ("events:visemes", ("t",))],
    "viewer": [("curve:*", ()), ("matrix:spectrum128", ()), ("events:*", ()), ("file:lyrics/lyrics.json", ("lines", "words")),
               ("file:meaning/meaning.json", ("sections", "characters", "do_not")), ("audio:preview", ()), ("audio:{stem}", ())],
    "frames": [("curve:*", ()), ("events:*", ())],
}


# ============================================================================ helpers
def files_of(stage: str) -> list[FileDef]:
    return [f for f in FILES if f.stage == stage]


def events_of(stage: str) -> list[EventDef]:
    return [e for e in EVENTS if e.stage == stage]


def tables_of(stage: str) -> list[TableDef]:
    return [t for t in TABLES if t.stage == stage]


def producer_of_events(name: str) -> str:
    return event_def(name).stage


def producer_of_file(path: str) -> str | None:
    for f in FILES + RUNNER_FILES:
        if f.path == path:
            return f.stage
    for t in TABLES:
        if t.path == path:
            return t.stage
    for e in EVENTS:
        if e.file == path:
            return e.stage
    return None


def all_stages() -> list[str]:
    s = {f.stage for f in FILES} | {e.stage for e in EVENTS} | {t.stage for t in TABLES} | {c.stage for c in CHANNELS.values()}
    return sorted(x for x in s if not x.startswith("_"))
