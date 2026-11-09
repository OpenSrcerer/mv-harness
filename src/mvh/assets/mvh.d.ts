// Type declarations for lib/mvh.js (mv-harness contract v1.0.0-rc.2). Semantics: docs/CONTRACT.md §9.
// Every time is in seconds from the first sample of audio/mix.flac. Helpers never return NaN.

export const VERSION: string;
export const CONTRACT_VERSION: string;
export const EPS: number;
export const POLICIES: readonly ['linear', 'mean', 'max', 'hold'];
export const CURVE_RATE_HZ: number;
/** Sub-count names, sub 0..3 = "1 e & a" (16ths within a count). */
export const SUB_NAMES: readonly ['', 'e', '&', 'a'];

// ------------------------------------------------------------------------------------------- frames
/** fps is a number (taken literally: 23.976 is not 24000/1001) or [num, den]. */
export type Fps = number | [number, number];
/** Frame rule. Blender uses frame0 = 1. `early` samples at the window centre t_n + 1/(2F). */
export interface FrameRuleInput { fps: Fps; frame0?: number; early?: boolean; }
export type FrameRuleLike = FrameRuleInput | Fps | FrameRule;
export interface FrameRule {
  readonly __mvhRule: true; readonly num: number; readonly den: number; readonly frame0: number; readonly early: boolean;
  readonly fps: number; readonly half: number;
}
export type Policy = 'linear' | 'mean' | 'max' | 'hold';

export function frameRule(fr: FrameRuleLike): FrameRule;
/** t_n = (n - frame0) * den / num */
export function timeOf(n: number, fr: FrameRuleLike): number;
export function frameCentre(n: number, fr: FrameRuleLike): number;
export function frameWindow(n: number, fr: FrameRuleLike): [number, number];
/** floor(t * num / den + (early ? 0 : 0.5) + 1e-9) + frame0 */
export function frameOf(t: number, fr: FrameRuleLike): number;
/** ceil(duration * num / den - 1e-9): frames with time_of(n) < duration. */
export function frameCount(duration: number, fr: FrameRuleLike): number;
export function samplesInFrame(n: number, fr: FrameRuleLike, rate: number, nSamples: number): [number, number];
export function roundHalfEven(x: number): number;

// ------------------------------------------------------------------------------------------- pure helpers
export type NumArray = ArrayLike<number>;
export function lerpAt(v: NumArray, x: number): number;
export function holdAt(v: NumArray, x: number): number;
export function nanAwareAt(v: NumArray, x: number): number;
export function curveAt(v: NumArray, t: number, rate?: number, policy?: Policy, nanAware?: boolean): number;
export function curveFrame(v: NumArray, n: number, fr: FrameRuleLike, rate?: number, policy?: Policy, nanAware?: boolean): number;
export function flashSamples(tEvent: number, rate?: number): [number, number];

export interface BeatItem extends EventItem {
  beat_index: number; bar: number; beat_in_bar: number; beats_in_bar: number; in_pulse: boolean; strength?: number; conf?: number;
}
export interface CountItem extends EventItem {
  id: string; start_beat: number; len: number; first_count: number; partial: boolean; lead_in: boolean; in_pulse?: boolean;
  accents: number[]; phrase_id?: string | null; section_id?: string | null;
}
export interface PhaseValue { value: number; in_pulse: boolean; }
export interface CountValue {
  /** E001..; E000 = the synthesised 5-6-7-8 lead-in; null outside every count. */
  eight_id: string | null;
  /** 1..8 (5..8 in the lead-in); null outside every count. */
  count: number | null;
  /** 16th within the count: 0..3 = "1 e & a". */
  sub: number;
  phase: number | null; accent: number; partial: boolean; lead_in: boolean; in_pulse: boolean;
}
export function beatPos(t: number, beats: ArrayLike<BeatItem>): PhaseValue;
export function beatPhase(t: number, beats: ArrayLike<BeatItem>): PhaseValue;
export function barPhase(t: number, beats: ArrayLike<BeatItem>): PhaseValue;
export function countAt(t: number, beats: ArrayLike<BeatItem>, counts: ArrayLike<CountItem>): CountValue;

export interface EventItem { t: number; d?: number | null; id?: string; tier?: number; [field: string]: unknown; }
export interface EventAt<T extends EventItem = EventItem> { item: T; progress: number; t_in: number; t_left: number; }
export function eventAt<T extends EventItem>(items: T[], t: number): EventAt<T> | null;
export function eventAllAt<T extends EventItem>(items: T[], t: number): T[];
export function eventNext<T extends EventItem>(items: T[], t: number, minTier?: number | null): T | null;
export function eventPrev<T extends EventItem>(items: T[], t: number, minTier?: number | null): T | null;
export function eventBetween<T extends EventItem>(items: T[], t0: number, t1: number, minTier?: number | null): T[];
export function eventInFrame<T extends EventItem>(items: T[], n: number, fr: FrameRuleLike, minTier?: number | null): T[];

export interface SingingItem extends EventItem {
  d: number; character_id: string; voice_id: string; line_id: string; lead_backing: 'lead' | 'backing';
}
export interface SingerValue {
  character_id: string | null; voice_id: string | null; lead_backing: 'lead' | 'backing' | null; line_id: string | null; mouth_open: number;
}
export function singerAt(t: number, singing: SingingItem[], mouthOpen: (voiceId: string | null, t: number) => number): SingerValue[];

export interface NoteItem extends EventItem { d: number; midi: number; name: string; vel: number; conf: number; }
export interface VocalValue {
  voiced: boolean; midi: number; hz: number; conf: number; pitch01: number; phrase_id: string | null; note: NoteItem | null;
}
export function vocalAt(t: number, ch: Record<string, NumArray>, rate?: number, phrases?: EventItem[], notes?: NoteItem[]): VocalValue;

export interface TextureLayoutRaw { row0: number; rows: number; n: number; width: number; }
export function textureLayout(lengths: number[], width?: number): TextureLayoutRaw[];
export function packTexture(channels: NumArray[], width?: number): { data: Float32Array; height: number; layout: TextureLayoutRaw[] };
export function textureSample(data: NumArray, lay: TextureLayoutRaw, t: number, rate?: number, policy?: Policy): number;

export type PulseShape = 'exp' | 'linear' | 'smooth';
export interface PulseOptions { attack?: number; decay?: number; unit?: 's' | 'beats'; shape?: PulseShape; }
export type OscShape = 'sine' | 'saw' | 'square' | 'triangle';
export interface OscOptions { shape?: OscShape; periodBeats?: number; phase?: number; }
export function pulse(t: number, items: EventItem[], beats?: BeatItem[] | null, opts?: PulseOptions): number;
export function osc(t: number, beats: ArrayLike<BeatItem>, opts?: OscOptions): number;
export function spectrumRows(t: number, s: number, nFrames: number, rate?: number): (number | null)[];

// ------------------------------------------------------------------------------------------- song objects
export interface ChannelMeta {
  id: string; file: string; offset_bytes: number; n: number; rate_hz: number; unit: string; range: [number, number];
  norm: { method: string; of?: string; lo?: number; hi?: number } | null; resample: Policy;
  special: { nan?: 'unvoiced'; floor?: number } | null; twin: string | null; stage: string; description: string;
  [extra: string]: unknown;
}

export class Curve {
  readonly id: string;
  /** Raw samples (float32; NaN only in vocal.f0_hz / vocal.midi where unvoiced). Sample i is centred at i / rate. */
  readonly values: Float32Array;
  readonly rate: number;
  readonly meta: ChannelMeta;
  readonly policy: Policy;
  readonly nanAware: boolean;
  readonly n: number;
  /** Point value at t (lerp, nearest for hold, NaN-aware for pitch). */
  at(t: number): number;
  /** Value of video frame n under the channel's resample policy. */
  frame(n: number, fr: FrameRuleLike): number;
}

export interface TierOptions { minTier?: number | null; }
export class Events<T extends EventItem = EventItem> {
  readonly name: string;
  /** false when the file does not exist in this song folder (items is then empty). */
  readonly exists: boolean;
  readonly kind: 'event' | 'segment' | null;
  readonly fields: Record<string, { unit: string | null; type: string; description?: string }>;
  readonly provenance: Record<string, unknown>;
  readonly schema: string | null;
  /** All items, sorted by t (ties keep file order). */
  readonly items: T[];
  readonly length: number;
  /** Latest-starting item with d > 0 whose [t, t + d) contains t. */
  at(t: number): EventAt<T> | null;
  /** EVERY item whose [t, t + d) contains t (overlapping segments), sorted by t then file order. */
  allAt(t: number): T[];
  /** First item strictly after t. */
  next(t: number, opts?: TierOptions): T | null;
  /** Last item at or before t. */
  prev(t: number, opts?: TierOptions): T | null;
  /** Items with t0 <= item.t < t1. */
  between(t0: number, t1: number, opts?: TierOptions): T[];
  /** Items with frameOf(item.t) == n. */
  inFrame(n: number, fr: FrameRuleLike, opts?: TierOptions): T[];
  byId(id: string): T | null;
}

export interface LyricLine extends EventItem {
  id: string; d: number; text: string; section_id: string | null; text_group: string; repeat_group: string | null;
  conf: number; grade: 'A' | 'B' | 'C' | 'D'; first_word: string | null; n_words: number; backing: boolean;
  speaker_hint: string | null; timing_source: string;
  /** Joined from events/singing.json: character ids singing this line (lead first). */
  singer: string[];
  /** Joined from events/singing.json: voice ids singing this line (lead first). */
  voice_ids: string[];
}
export interface LyricWord extends EventItem { id: string; line_id: string; d: number; text: string; conf: number; flags?: string[]; }
export interface LyricValue { line: LyricLine | null; word: LyricWord | null; progress: number | null; word_progress: number | null; }

export interface MeaningValue {
  section_id: string | null; meaning: string | null; feel: string | null;
  emotion: { lyric: string | null; audio: string | null; agree: boolean | null } | null;
  palette_hint: string[]; movement_hint: string | null; camera_hint: string | null; characters_present: string[];
  /** Global do-not rules (the user's words) followed by the section's own, de-duplicated. */
  do_not: string[];
  provenance: { source: string; status: string; cites: unknown[] } | null;
  /** meaning.json status: user | draft | pending (null without meaning.json). */
  status: 'user' | 'draft' | 'pending' | null;
  /** D54: the section's field_sources from meaning.json (field -> 'user' | 'draft' | ...); {} when none. */
  field_sources: Record<string, string>;
}

export interface TextureLayout { id: string; row0: number; rows: number; n: number; rate: number; width: number;
  /** vec4 for mvhCurve(tex, t, info): (rate, n, width, row0). */
  info: [number, number, number, number]; }
export interface TextureData<D extends Float32Array | Uint8Array = Float32Array | Uint8Array> {
  /** Row-major [height x width]. r32f: Float32Array; r8: Uint8Array (round(clamp(value, 0, 1) * 255)). */
  data: D; width: number; height: number; format: 'r32f' | 'r8'; layout: TextureLayout[];
}
export interface TextureOptions { layout?: 'wrap'; width?: number; format?: 'r32f' | 'r8'; }

export const VIZ: Readonly<{
  NUM_BANDS: 128; WAVE_LEN: 512; F_MIN: number; F_MAX: number; BEAT_DECAY_S: number; PULSE_DECAY_S: number; PEAK_FALL_PER_S: number;
  BEAT_STRENGTH_MIN: number; PULSE_STRENGTH_MIN: number; RECENT_BEATS: number; RECENT_BEAT_EMPTY: number;
  HIT_RELEASE: number; HIT_THRESHOLD: number; KICK_GATE_DB: number; HIT_FLOOR: number; REF_FLOOR: number; REARM_DB: number;
  RANGE_T: Readonly<{ bass: readonly [number, number]; mid: readonly [number, number]; high: readonly [number, number] }>;
  BEAT_WINDOW_S: number; PEAK_WINDOW_S: number; DEFAULT_FPS: number;
}>;

/** The viz/js/audio.js AudioEngine fields, computed offline for one frame. */
export class VizState {
  /** Frame centre the state was computed for, and the frame number. */
  t: number; frame: number;
  bands: Float32Array; bandsRaw: Float32Array; peaks: Float32Array;
  /** RGBA x 128: R = G = B = round(255 * band value), A = 255. */
  bandBytes: Uint8Array;
  /** 512 zeros / 512 x 128: the waveform is not stored. */
  wave: Float32Array; waveBytes: Uint8Array;
  bass: number; mid: number; high: number; level: number;
  kick: number; kickRaw: number; midHit: number; highHit: number;
  beat: number; beatPulse: number; onset: boolean; beatCount: number;
  midPulse: number; midOnset: boolean; highPulse: number; highOnset: boolean;
  /** Last 8 bass onset times (song seconds; -100 = none), oldest first; use song time as the scene clock. */
  recentBeats: Float32Array; recentBeatAmp: Float32Array;
  bpm: number; gain: number; sensitivity: number; drive: { bass: number; mid: number; high: number }; monitorVolume: number;
  hitRelease: number; hitThreshold: number; kickGateDb: number; hitFloor: number; refFloor: number; rearmDb: number;
  silentFor: number; active: boolean; sourceType: 'offline'; sourceLabel: string;
  ranges: Record<'bass' | 'kick' | 'mid' | 'high' | 'flux' | 'fluxMid' | 'fluxHigh', [number, number]>;
  bandAt(t: number): number; bandLow(x: number): number; bandMid(x: number): number; bandHigh(x: number): number;
  update(): void; on(): this;
}

export type HelperName = 'beatPos' | 'beatPhase' | 'barPhase' | 'osc' | 'pulse' | 'count' | 'lyricAt' | 'vocalAt' | 'singerAt' |
  'meaningAt' | 'spectrumAt' | 'spectrumWindow' | 'vizState';
export const HELPER_NEEDS: Readonly<Record<HelperName, string[]>>;

/**
 * What ensure()/include accept: 'all'; 'curves:*' / 'events:*'; 'curves:<file id>' (core, stems, vocal, chroma12,
 * instruments_1hz, mood_1hz, spectrum128); 'events:<name>'; 'lyrics'; 'meaning'; 'spectrum'; 'helper:<HelperName>';
 * or a bare curve file id, channel id or events name.
 */
export type ResourceSpec = string | string[];

export class Song {
  /** Folder path or base URL. */
  readonly base: string;
  readonly manifest: Record<string, any>;
  readonly index: { files: Record<string, any>; channels: ChannelMeta[]; [k: string]: any };
  /** Seconds (manifest.source.duration_s). */
  readonly duration: number;
  readonly eventNames: string[];
  readonly channelIds: string[];
  readonly beats: BeatItem[];
  hasCurve(id: string): boolean;
  resolve(spec: ResourceSpec): string[];
  /** Load resources so the next synchronous calls are safe (Remotion: inside delayRender/calculateMetadata). */
  ensure(spec: ResourceSpec): Promise<void>;
  isLoaded(spec: ResourceSpec): boolean;

  curve(id: string): Curve;
  events<T extends EventItem = EventItem>(name: string): Events<T>;
  frameCount(fr: FrameRuleLike): number;

  pulse(src: string, t: number, opts?: PulseOptions): number;
  osc(t: number, opts?: OscOptions): number;
  beatPos(t: number): PhaseValue;
  beatPhase(t: number): PhaseValue;
  barPhase(t: number): PhaseValue;
  count(t: number): CountValue;
  lyricAt(t: number): LyricValue;
  vocalAt(t: number): VocalValue;
  singerAt(t: number): SingerValue[];
  meaningAt(t: number): MeaningValue;
  /** Uint8Array(128): nearest spectrum row; value / 255 = viz band value (same as viz bandBytes R). */
  spectrumAt(t: number): Uint8Array;
  /** Uint8Array(k * 128), k = round(100 * s) + 1 rows, oldest first, zero rows outside the song. */
  spectrumWindow(t: number, s: number): Uint8Array;
  textureData(ids: string | string[], opts?: TextureOptions): TextureData;
  /** viz/js/audio.js fields at the frame containing t. The frame rule is mandatory: pass fr, or set it once with load(base, {fr}); throws without one. */
  vizState(t: number, fr?: FrameRuleLike | null): VizState;
}

export interface LoadOptions {
  /** Custom fetch (browsers / Remotion); defaults to globalThis.fetch. */
  fetch?: (url: string) => Promise<Response>;
  /** Resources to load eagerly (see ResourceSpec). */
  include?: ResourceSpec;
  /** Song-wide default frame rule used by vizState(t) when no fr is passed. */
  fr?: FrameRuleLike | null;
}
/** base: a URL (browser) or a folder path (Node). */
export function load(base: string | URL, opts?: LoadOptions): Promise<Song>;
/** Node only: synchronous open; lazy parts are read on first use. */
export function loadSync(path: string, opts?: { fr?: FrameRuleLike | null }): Song;

declare const _default: {
  load: typeof load; loadSync: typeof loadSync; frameOf: typeof frameOf; timeOf: typeof timeOf; frameCount: typeof frameCount;
  frameCentre: typeof frameCentre; frameWindow: typeof frameWindow; Song: typeof Song; VIZ: typeof VIZ;
};
export default _default;
