"""The runner (W1b runtime): DAG, cache, scheduler, worker, locks, models, finalize, doctor.

The frozen stage interface is in ``spec``. Importing this package imports only ``spec`` (stdlib +
mvh.contract.ids), so the sep worker can use ``mvh.runner.threads`` and ``mvh.runner.locks``.
"""

from .spec import (  # noqa: F401
    Audio,
    Ctx,
    Curve,
    ExternalInput,
    MissingFixture,
    ModelHandle,
    Output,
    StageError,
    StageResult,
    StageSpec,
    UndeclaredDependency,
    UndeclaredOutput,
    Upstream,
    Writer,
    catalog_outputs,
    check_dag,
    load_stage_specs,
    topo_order,
)
