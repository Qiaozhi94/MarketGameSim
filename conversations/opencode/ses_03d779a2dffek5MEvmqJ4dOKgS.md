---
tool: "opencode"
tool_name: "OpenCode"
session_id: "ses_03d779a2dffek5MEvmqJ4dOKgS"
title: "Phase 6 确定性与验收 (@Sisyphus-Junior subagent)"
project: "D:/Projects/market-game-sim"
model: "glm-5.2"
created_at: "2026-08-02T12:52:26Z"
updated_at: "2026-08-02T12:52:27Z"
tokens_input: 0
tokens_output: 0
cost: 0.0
parent_id: "ses_03dca8ceeffer5HK1H5NpzxJb9"
---

# Phase 6 确定性与验收 (@Sisyphus-Junior subagent)

## user · 2026-08-02T12:52:26Z

You are implementing the **final phase — Phase 6** of milestone **0.1.1 (minimal deterministic kernel, no leverage)** in the project `D:\Projects\market-game-sim`.

# CURRENT STATE

- Phase 1-5: ALL DONE. 679 tests pass.
- `src/market_game_sim/rng/`: EMPTY (needs T601)
- `src/market_game_sim/kernel/runner.py`: EventKernel works
- `src/market_game_sim/book/`: orderbook + matching + simulator
- `src/market_game_sim/ledger/`: account + fees + conservation + reserved
- `src/market_game_sim/eventlog/`: writer + digest + termination + bootstrap
- `src/market_game_sim/hook/`: regime interface + crypto_perp stub
- `src/market_game_sim/config/`: parser + validator + serializer + types
- `src/market_game_sim/schema/`: registry + event_fields.json + constraints

# TASK LIST (all 7 Phase 6 tasks)

The full task definitions are in `specs/v0.1-belief-testing-laboratory/0.1.1-minimal-kernel/tasks.md` lines 252-291. Read that file first.

**T601** [代理策略 §10.1-§10.2] [P] **RNG**: `blake2b` length-prefix semantic key → uniform in [0,1). **Do NOT use `SeedSequence`** (NumPy, not stdlib). 0.1.1 only needs uniform distribution — others (normal, power-law) come in 0.1.2.

Build `src/market_game_sim/rng/__init__.py` with:
- `SeedRng(seed: int)` — deterministic PRNG using blake2b
- `uniform(seed_bytes: bytes, counter: int) -> float` — returns uniform [0, 1) via blake2b digest interpreted as fraction (like `int.from_bytes(h, 'big') / 2**(len(h)*8)`)
- Semantic key construction: `seed_bytes = master_seed.to_bytes(8, 'big') + run_id.encode() + purpose.encode() + counter.to_bytes(8, 'big')`

**T602** [SC-002] [TDD] **确定性断言**: same config + same seed, two runs in **different processes** with **different `PYTHONHASHSEED`** (e.g. 1 and 2) → same event digest hash. **Fixed same seed is NOT enough** — same seed makes `hash()` misuse pass. Use `hashlib.blake2b` for digest, NOT built-in `hash()`.

Build `tests/unit/rng/test_determinism.py` that:
- Runs a simulation twice with different PYTHONHASHSEED
- Computes the event digest hash (using blake2b on committed records)
- Asserts the two hashes are identical

**T603** [SC-006] [事件 Schema §5.2] [TDD] **独立验证器 `verify`**: Read-only event log, **does NOT import `kernel/` or `ledger/`** — if it reuses kernel code, it cannot prove the log is self-contained. Rebuilds **both** account and book final states, validates causal chain reference integrity, validates C1/C2, validates every `transaction_seq` starts at `record_index=0` and has no gaps.

**Order book reconstruction is a 0.1.1 requirement** (事件 Schema §4.7 claims the book can be derived from ORDER_ARRIVAL − Σ fills − Σ cancels). Must cover: partial fill, IOC remainder cancel, STP cancel, agent-initiated cancel — 4 paths. Assert aggregate qty per price level matches kernel snapshot.

Build `src/market_game_sim/verify.py` as a CLI-compatible module. Read `eventlog/writer.py` and `eventlog/termination.py` for log format.

**Termination discriminator: structural then semantic** (order must not be reversed): first validate JSON integrity / first-and-last records / `record_count`, any failure → **TI-5** and STOP (don't read `terminated`). Only when structural checks pass, check `terminated`: `ABORTED` → **TI-4`. Must NOT return TI-4 for truncated ABORTED logs (combined case from T204e2).

**T604** [KR-005] [TDD] **Import check**: core domain layer has no NumPy/pandas/etc. third-party imports. Build `tests/unit/test_core_imports.py` that greps `src/market_game_sim/` (excluding `config/` which needs pyyaml, and `tests/`) for numpy, pandas, scipy, matplotlib, sklearn, torch, tensorflow.

**T605** [plan §5.2] **Property test**: Random order flow (extreme prices, boundary quantities, self-trade, cross-level) with C1/C2 always holding, queue_key / log_key each strictly increasing, state machine no illegal transitions.

Build `tests/property/test_random_orders.py` using `pytest` parameterized tests (or stdlib random for generating order flows). Generate random order sequences, run them through the simulator, assert:
- C1: Σ position ≡ 0 after every event
- C2: Σ (wallet − entry_notional) + exchange_fee + risk_pnl = Σ wallet(0) after every event
- queue_key strictly increasing
- log_key strictly increasing
- No accepted=false orders (all pass admission stub)

**T606** [NFR-002] **Coverage**: orderbook + ledger branch coverage ≥ 90%. Add `--cov=src/market_game_sim/book --cov=src/market_game_sim/ledger --cov=src/market_game_sim/kernel --cov-report=term-missing` to pytest. If coverage is below 90%, add targeted property tests or edge case tests.

**T607** [spec §需求追踪矩阵] [TDD] **Matrix validator** (退出条件 E10): Only parse `specs/v0.1-belief-testing-laboratory/traceability.json`, not Markdown. Validate: (1) JSON IDs == spec declared IDs; (2) milestone directory + spec.md exist; (3) referenced exit condition IDs exist in that milestone's exit condition table; (4) `status=owned` without `owners` → fail; (5) spec display table matches JSON.

Three negative fixtures: (a) delete 0.1.4 mapping; (b) delete a stage owner (like FR-004's 0.1.2 slice); (c) create scope overlap. All three must make CI fail.

Build `tests/unit/test_traceability.py` that exercises T607.

# EXISTING FILES TO READ

- `src/market_game_sim/kernel/runner.py` — EventKernel API
- `src/market_game_sim/book/simulator.py` — `run_simulation()` helper
- `src/market_game_sim/book/matching.py` — match_order handler
- `src/market_game_sim/book/orderbook.py` — Book class
- `src/market_game_sim/ledger/account.py` — Account, apply_fill
- `src/market_game_sim/ledger/conservation.py` — C1/C2 check
- `src/market_game_sim/eventlog/writer.py` — write_log, serialize_event
- `src/market_game_sim/eventlog/digest.py` — blake2b digest
- `src/market_game_sim/eventlog/termination.py` — classify_log (TI-4, TI-5)
- `src/market_game_sim/eventlog/bootstrap.py` — build_account_payload
- `src/market_game_sim/config/parser.py` — ParsedConfig
- `src/market_game_sim/schema/registry.py` — SchemaRegistry
- `src/market_game_sim/schema/event_fields.json` — schema
- `tools/validate_contract_sources.py` — existing validator (T607 reference)
- `specs/v0.1-belief-testing-laboratory/traceability.json` — traceability matrix (T607)

# IMPLEMENTATION REQUIREMENTS (MUST DO)

1. **TDD first for all [TDD] tasks**

2. **No breaking changes**: All 679 existing tests must still pass.

3. **Stdlib only in domain layer** (KR-005).

4. **Integer-only arithmetic** in kernel. No float in domain logic (except RNG which produces uniform [0,1) float — that's the one exception).

5. **T603 verify**: Must NOT import `kernel/`, `ledger/`, `book/` — truly independent. It reads JSONL event log, parses records, rebuilds state. Can import `eventlog/` (writer/termination format) but not kernel/business logic. Build as `src/market_game_sim/verify.py` with CLI interface.

6. **T603 verify scope**: Rebuild both accounts (wallet, position, entry_notional, reserved, realized_pnl, state) AND order book (aggregate qty per price level, bid descending / ask ascending). Validate causal chain: every `caused_by_event_id` points to an existing `event_id` in a prior transaction. Validate record_index starts at 1 for each transaction. Validate C1/C2 at every step.

7. **T605 property test**: Generate at least 200 random order sequences. Use the existing `match_order` handler and `run_simulation()` helper. Don't implement a separate matching engine — use the one already built.

8. **T606 coverage**: Run `pytest --cov=src/market_game_sim/book --cov=src/market_game_sim/ledger --cov-report=term-missing` and add tests to reach ≥90% branch coverage.

9. **Update tasks.md**: Mark T601-T607 as `[x]`.

10. **Run `python -m pytest tests/ -x --tb=short` at the end**: All tests must pass.

# MUST NOT DO

1. Do NOT modify `event_fields.json`, `kernel/runner.py`, `eventlog/` core modules.
2. Do NOT import numpy/pandas/etc. in domain layer.
3. Do NOT use `SeedSequence` or NumPy RNG.
4. Do NOT use built-in `hash()` for deterministic digests — use `hashlib.blake2b`.
5. Do NOT commit.

# EXPECTED OUTCOME

- All 7 Phase 6 tasks completed
- New tests: T601 (RNG), T602 (determinism), T603 (verify), T604 (imports), T605 (property), T606 (coverage), T607 (traceability)
- `python -m pytest tests/ -x --tb=short` shows 100% pass
- `tasks.md` updated with `[x]` for T601-T607
- Summary report

# WORK APPROACH

1. Read tasks.md lines 252-291
2. T601: Build rng/ module, test
3. T602: Determinism test with cross-PYTHONHASHSEED runs
4. T603: Build verify.py (hardest — independent event log verifier)
5. T604: Import check test
6. T605: Property test with random order flow
7. T606: Coverage check + additional tests
8. T607: Traceability matrix validator
9. Update tasks.md + final test run + report

You have full context. Begin.
<!-- OMO_INTERNAL_INITIATOR -->
