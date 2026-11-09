"""The stage list of PLAN §3.2 (frozen names). Deps live in each stage's STAGE spec (mvh.stages.<name>)."""
from __future__ import annotations

#: every analysis stage, in PLAN §3.2 table order
ANALYSIS_STAGES: tuple[str, ...] = (
    "ingest", "identity", "separate_fast", "separate_hq", "allin1", "spectral", "loudness", "rhythm", "harmony",
    "dynamics", "structure", "stem_activity", "drums", "instruments", "notes", "vocals", "mood", "lyrics", "voices",
    "lipsync", "choreo", "cues", "meaning",
)
#: stages that consume everything (brief, viewer) or run on demand (frames)
FINAL_STAGES: tuple[str, ...] = ("brief", "viewer", "frames")
STAGE_NAMES: tuple[str, ...] = ANALYSIS_STAGES + FINAL_STAGES

__all__ = ["ANALYSIS_STAGES", "FINAL_STAGES", "STAGE_NAMES"]
