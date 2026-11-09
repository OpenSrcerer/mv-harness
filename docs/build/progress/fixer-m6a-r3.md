# fixer-m6a-r3
- Done: edit.js undo fix (save() takes the popped entry, failure branch restores it; undo() ignored while saving).
- tests/review/M6a (15) and tests/unit/viewer pass directly (52 total incl. r3 test).
- Next: gate.ps1 M6a (slow, machine contended); report.
gate done; determinism fails upstream
