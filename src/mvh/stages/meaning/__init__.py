"""meaning stage (contract v1, owner M6b): PLAN §8, CONTRACT §7 (meaning files), D3, D5, D7, D38.

Interview, drafting bundle (request.md, input.json, schema.json), merge of the user's intent and an agent/LLM draft
with provenance on every claim (user > draft > harness facts), re-anchoring of per-section claims by time overlap
(orphans.json), events/singing.json and lyrics/lines.tsv (singer = characters, lead first, ``C1+C2``).

``meaning/intent.md`` and ``meaning/authored.json`` are INPUTS: read here, never written or deleted.

Params: ``draft`` = agent (default: the calling agent drafts from request.md) | anthropic (``mvh meaning --draft
anthropic`` writes authored.json through the API, then merges) | off; ``lyrics_to_agents`` = true (false blanks the
text column of lines.tsv and keeps lyrics out of the drafting bundle: --no-lyrics-to-agents).
"""
from mvh.runner.spec import ExternalInput, StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "meaning",
    ('identity', 'lyrics', 'voices', 'structure', 'mood', 'vocals', 'instruments', 'cues'),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("meaning"),
    params={'draft': 'agent', 'lyrics_to_agents': True},
    external_inputs=(ExternalInput("intent", "meaning/intent.md", False, "user answers"), ExternalInput("authored", "meaning/authored.json", False, "agent/LLM draft (status draft)"),),
    module="M6b",
    description='Interview, request bundle, merge of user intent and drafts with provenance, singing.json, lines.tsv, orphans.',
)


def run(ctx) -> StageResult:
    from .stage import run as _run

    return _run(ctx)
