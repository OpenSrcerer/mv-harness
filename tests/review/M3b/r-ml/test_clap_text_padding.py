# ruff: noqa: E501  (long docstrings / evidence lines)
"""R-ML M3b (major): CLAP text prompts are embedded in a padded batch without an attention mask.

The pinned Xenova export ``text_model_quantized.onnx`` has ONE input, ``input_ids`` (no ``attention_mask``).
``instruments.clap.Clap.text`` tokenises all prompts with ``padding=True`` and runs them as one batch, so every prompt
shorter than the longest one is encoded WITH its ``<pad>`` tokens attended to. The model was trained with padding
masked out, so the embedding of a prompt depends on which other prompts share its batch. (The model is also
dynamically quantized, so even the longest, unpadded prompt moves a little with its batch: cos 0.9865.)

Measured (reviewer probe): cos(batch, alone) = 0.843 for "a deep synth bass line" (the shortest synth sub-type
prompt), 0.97-0.99 for the others; the user term "bass" batched with one longer term: cos 0.594. On a sawtooth pad the stage's synth sub-type split (softmax at T = 0.01) moves from
pad/lead = 0.51/0.49 (batched) to 0.004/0.996 (each prompt alone). The same applies to the neutral baseline and to the
user's ``params.vocabulary`` terms: a user term's ``inst.term_<slug>`` curve changes when the user adds another,
longer term.

Fix: encode each prompt alone (batch of 1, no padding), or re-export the text model with ``attention_mask``.
"""
from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.real

SYNTH_PROMPTS = ("a soft sustained synthesizer pad", "a bright lead synthesizer melody",
                 "an arpeggiated synthesizer sequence", "a deep synth bass line")


def test_prompt_embedding_does_not_depend_on_its_batch(clap):
    from mvh.testing import heavy

    with heavy("r-ml-m3b-test", threads=3):
        batched = clap.text(list(SYNTH_PROMPTS))
        alone = np.concatenate([clap.text([p]) for p in SYNTH_PROMPTS])
    cos = (batched * alone).sum(axis=1)
    bad = {p: round(float(c), 4) for p, c in zip(SYNTH_PROMPTS, cos) if c < 0.999}
    assert not bad, f"padded-batch embeddings differ from single-prompt embeddings (cosine): {bad}"


def test_user_term_embedding_is_independent_of_other_terms(clap):
    """``params.vocabulary`` = ["bass"] vs ["bass", <a longer term>]: the 'bass' term curve must not change."""
    from mvh.testing import heavy

    with heavy("r-ml-m3b-test", threads=3):
        solo = clap.text(["bass"])[0]
        with_other = clap.text(["bass", "a distorted electric guitar playing a fast solo"])[0]
    cos = float(solo @ with_other)
    assert cos > 0.999, f"user term 'bass' embedding changes with the other vocabulary terms (cos {cos:.4f})"
