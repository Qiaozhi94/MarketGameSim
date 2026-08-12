"""0.1.4 T301/T302: Report layer.

Consumes frozen artifacts declared in a manifest, validates them against
``report_artifacts.json``, and produces ``report.json`` (machine-readable
truth source) + ``report.md`` (human-readable, rendered FROM report.json).

Does NOT import ``kernel/``, ``book/``, ``ledger/``, or ``eventlog``
(NFR-004 / E5).
"""
