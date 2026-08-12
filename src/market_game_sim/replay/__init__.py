"""0.1.4 T101-T103 / T201-T204: Replay layer.

Consumes an event log JSONL and rebuilds per-frame state (accounts, order
book, price) to produce a single-file HTML frame-by-frame replay (E1/E2/E6).

This package is a read-only consumer of the log: it MUST NOT import
``kernel/``, ``book/``, ``ledger/``, or ``eventlog/`` (NFR-004 / E5).  The
only channel between it and the kernel is the log file.
"""
