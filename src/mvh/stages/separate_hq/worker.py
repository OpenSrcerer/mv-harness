"""Sep-worker entry for separate_hq (``mvh.worker separate_hq job.json`` imports this). The job lives in
``mvh.sep.hq_worker`` (stdlib + numpy at import; torch and audio-separator inside run_job)."""

from mvh.sep.hq_worker import run_job

__all__ = ["run_job"]
