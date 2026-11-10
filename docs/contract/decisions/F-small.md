# F-small decisions
- intent.md: `*`, bullet, en/em dash and dash+NBSP bullets directly under a bare template key are normalised to `- ` items (not silently a note).
- A stray `key: value` line beside failed `- ` items under a list key is a note (warned), never the only rule; a deeper stray line under a plain `- text` item is its own entry.
- Runtime: a song.lock whose pid cannot be queried and that predates the last boot is stale (locks.boot_time).
- Manifest: kept stages keep summary/warnings/fallback/degraded flags; kept stages whose curves were dropped as unfit (other audio) are not listed.
