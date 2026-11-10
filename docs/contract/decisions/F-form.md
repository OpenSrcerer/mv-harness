# F-form: honest section labels (ffix-form, final fix pass; structure 1.5.0)

Owner: M2 structure. Fixes S09 (rap songs over-labelled chorus), W4V2-JEREMY-HOOK-VERSE and W4V2-FORMRULE-NARROW.

## F-form-1 A `chorus` label needs repetition evidence (interpretation of `sections.label`)
allin1 votes `chorus` on texture, not on recurrence, so a rap verse over a looped beat reads as chorus. In the informative
(allin1) labelling path, a repeat group keeps `chorus` only when all three hold (structure's deps only, no lyrics):
1. **recurrence**: >= 2 separate occurrences of the group (runs of consecutive member sections; silence does not separate);
2. **a refrain, not the ground**: the group covers <= `chorus_max_share` (0.55) of the non-silent song;
3. **consistency**: allin1's chorus minus verse probability, averaged over the occurrences, >= `chorus_min_margin` (0.15).

A non-recurring chorus group or singleton that is a near-repeat of a recurring chorus group (mean similarity >=
`chorus_near_repeat` (0.6) x that group's own within-group similarity) and that allin1 still calls chorus over verse keeps
`chorus`. Otherwise the group falls back to allin1's best non-chorus label (verse when nothing else has weight), with two
form slots: a lone part between two occurrences of the same recurring chorus is `bridge`; a non-recurring run after the last
chorus that runs into the outro is `outro` (the coda). The fallback's `conf` is allin1's probability of the new label.
The structural (EDM) labelling path is unchanged.

## F-form-2 Hook stretch (W4V2-JEREMY-HOOK-VERSE)
A non-repeated section labelled `verse` that sits next to an occurrence of a recurring chorus group, is a near-repeat of it
(ratio >= `chorus_near_repeat`) and is closer to it than to every repeated verse group by >= `hook_verse_margin` (0.1) is
`chorus`, except in the slot right before that chorus's first occurrence (the verse leading in).

## F-form-3 Verse before the first chorus (W4V2-FORMRULE-NARROW)
The W4-AN-11(d) rule (a non-repeated `chorus` right before the first occurrence of a different, repeated chorus group is the
verse) now relies on the form condition alone: `verse_min_before_chorus` defaults to 0.0 (was 0.25, fitted to synth_sr32).

## F-form-4 Additive field `sections.label_evidence` (string[])
Every section carries a short human-readable reason for its label (e.g. `chorus: recurring refrain (group C: 2 occurrences,
12% of the song, allin1 chorus-verse +0.64)`, `verse: allin1 said chorus but no repetition evidence (...)`, `form: ...`,
`edm role drop`, `silent`, `user override (structure.labels)`). Together with the existing `conf` (label confidence 0..1) and
`label_probs`, agents can see how much to trust a label. Additive, declared through the events writer `fields`; no frozen
field changes. New params: `chorus_min_margin`, `chorus_max_share`, `chorus_near_repeat`, `hook_verse_margin`.

## Measured (structure re-run on cached upstreams, out/_wip/ffix-form/dev)
- Newton vs Nye: chorus 7/14 -> 0/14 (11 verse, 2 outro, 1 silence).
- Jeremy: chorus 10/18 -> 7/18; 176.12 s hook section verse -> chorus; the 220-288 s vamp (one occurrence, no lead lyrics)
  chorus -> outro. Same labels on jeremy_gm6 / jeremy_gm12 (level invariance).
- Synth: truth labels (intro, verse, chorus, bridge, chorus, outro) on all 11 variants incl. sr22 (was intro, chorus, chorus,
  bridge, chorus, outro), tempo 0.9/0.95/1.1, sr32/48, gain +-12 dB, mp3.
- MEGAFAUNA, Versatile and their gain copies: sections and EDM roles identical to before.
