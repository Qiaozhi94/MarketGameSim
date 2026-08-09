---
tool: "opencode"
tool_name: "OpenCode"
session_id: "ses_0199c8561ffe6e9RFzYXEdf3VU"
title: "Map experiment run wiring for E1-E5 (@explore subagent)"
project: "D:/Projects/market-game-sim"
model: "claude-haiku-4-5"
created_at: "2026-08-09T11:58:26Z"
updated_at: "2026-08-09T11:58:27Z"
tokens_input: 0
tokens_output: 0
cost: 0.0
parent_id: "ses_01a6d8622ffei5cBRUTyC14Unq"
---

# Map experiment run wiring for E1-E5 (@explore subagent)

## user · 2026-08-09T11:58:26Z

I'm about to run real experiments for the 0.1.3 exit checklist (E1-E5) in MarketGameSim at D:\Projects\market-game-sim. I need to know exactly how to wire and run a real robustness study through the existing machinery, so my E1-E5 evidence runs are correct.

GOAL: Map how to run real experiments end-to-end: config -> run -> per-cell classification -> paired effect -> reports.

DOWNSTREAM: I'll write an experiment script that runs: 2 behavior mappings x 2 model families cross matrix, parameter scan, 5-factor ablation, holdout zone, and produces evidence for E1-E5. I need exact APIs.

READ AND REPORT on these files:
1. src/market_game_sim/experiment/runner.py — full run_one / run_multi_seed / run_paired / build_study_report / build_market_validation_report signatures and the world dict structure: how is `world` built in run_one, what keys does it set (agent_specs, behavior_mapping, maint_bp, experiment_seed, etc.), and where would a caller inject a behavior_mapping target_fn (I added `world.get("behavior_mapping", target_position)` in _dispatch_agents — confirm it's wired).
2. src/market_game_sim/agent/handler.py — how _compute_belief_signal works: the five factors, belief_weights (dirichlet), noise_factor draw; is there ANY concept of "model family" in the agent code, or is the only agent model the factor-based belief agent? What would a second "model family" (e.g. a direct-signal or momentum-only family) require at the code level?
3. src/market_game_sim/experiment/config.py — ExperimentConfig fields and AgentSpec fields (agent/scheduler.py), especially leverage_tier, max_order_qty, is_market_maker.
4. src/market_game_sim/agent/mapping.py — the BehaviorMapping interface, LinearMapping, ThresholdMapping, get_mapping — exact signatures so I can inject mapping.target_position into a run.
5. How does run_one compute RunResult? What fields are available (classification, liquidation_metrics, accounts, events, exchange_fee_units, exchange_risk_pnl_units, initial_baseline)?
6. src/market_game_sim/robustness/ — the modules I built: preregistration.py (Preregistration dataclass + freeze), zones.py (cell_id/run_id), grid.py (expand_grid), pairing.py (pair_id/arm_id/aggregate_pairs), cross_matrix.py (CrossMatrix.report), market_sufficiency.py, cross_sufficiency.py, ablation.py (ablated_weight_vector/leave_one_out_disabled), cell_classify.py (classify_cell), boundary.py (locate_failure_boundary), refinement.py, holdout.py, holdout_run.py, paired_stats.py (paired_bootstrap), report_2part.py, final_conclusion.py, zero_sum.py, evidence_matrix.py, archive.py, performance.py, bridge_check.py, report_guard.py, determinism.py. For each: one-line summary of what it needs as input to produce its output.
7. docs/experiments/0.1.2-e6-demonstration-run.md + .json — the 0.1.2 demonstration run pattern: config (2 MM + 20 retail, 5 seeds, 30000 transactions), what it produced, and how it was documented. This is my template for an E1-E5 demonstration run.

Report concrete signatures, world-dict keys, and the minimal wiring to run a real robustness study. Be thorough.
<!-- OMO_INTERNAL_INITIATOR -->
