"""mv-harness output contract (PLAN §4). Stdlib + numpy only (worker rule, PLAN §3.3).

Modules:
  ids          ID formats, regexes, helpers (§4.3)
  conventions  REFERENCE time/frame/resample/helper semantics (§4.2, §4.4, §4.5) - loaders must match it
  registry     curve channel registry (ids, units, ranges, resample policies, norms)
  catalog      every output file and events name with frozen fields; the Consumed-by matrix
  schemas      JSON Schema 2020-12 build/load/validate (validate needs jsonschema: main env)
  curvefile    curves/*.f32 + index.json packer/reader
  events       event-file envelope reader/writer
  fixture      walking-skeleton stub behaviour (copy outputs from tests/contract/synth/)
  gen          python -m mvh.contract.gen [--check]: regenerate schema/ and docs/CONTRACT.md tables
"""
from .catalog import CONTRACT_VERSION, SCHEMA_BASE

__all__ = ["CONTRACT_VERSION", "SCHEMA_BASE"]
