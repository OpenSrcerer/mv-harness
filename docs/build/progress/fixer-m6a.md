# fixer-m6a progress
Done: F-PLAYHEAD (audio.js setPlaying arms rAF), F-OPTIONAL-EVENTS / F-FATAL-ABSENT (data.js markAbsent + guarded ev()),
F-SAVE-LOST (edit.js api() catches network errors; server 503 on write failure), F-NAN (strict JSON in/out, finite walk),
F-CLOBBER (read_overrides_checked: invalid file -> GET error + POST 409, file untouched; page toasts it),
F-INTENT-LS (all splitlines separators flattened; parse splits on \n only).
Commands: powershell.exe -NoProfile -File scripts/run.ps1 python -m pytest -q tests/review/M6a tests/unit/viewer  -> 61 passed.
Next: gate.ps1 M6a result.
Gotcha: this tool collapses double backslashes in heredocs; use the Edit tool for Python source edits.
Gate result: unit+determinism fail for non-viewer reasons (see report).
