"""0.1.3 model-robustness infrastructure.

This package hosts the 0.1.3 milestone's dedicated machinery that does not
belong in the 0.1.2 experiment layer: the startup admission gate (T001),
preregistration (T003/T005), model-family registration (T006), parameter
grid expansion (T202) and the paired/holdout robustness report (T601+).

Layer rule (design.md §2): this is L3 (experiment orchestration) territory --
it may import L1/L2 modules but nothing above it; it must not be imported by
kernel/ book/ ledger/ eventlog/ or agent/.
"""
