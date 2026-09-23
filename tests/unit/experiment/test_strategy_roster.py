"""0.4.1 T962 (DR-501 / NFR-502 / AC-503): StrategyRoster schema and rebuild.

Locks: the roster id is derived from content (any field change moves it, key
order does not); a roster rebuilds from its id and refuses tampered files;
validation is closed-world with stable codes; the anchor schema is frozen but a
roster that asks for an unimplemented anchor fails closed instead of running
without one; the same roster reproduces the same run.
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from market_game_sim.experiment.config import compute_config_hash
from market_game_sim.experiment.roster import (
    RosterError,
    build_agent_specs,
    build_experiment_config,
    load_roster,
    parse_roster,
    save_roster,
)
from market_game_sim.experiment.runner import run_one


def _body() -> dict:
    return {
        "schema_version": 1,
        "seed": 7,
        "engine": {
            "initial_price_ticks": 10_000,
            "mult": 1000,
            "maker_bps": -1,
            "taker_bps": 5,
            "maint_bp": 500,
            "target_bp": 1000,
            "liquidation_latency_ns": 1_000_000,
        },
        "bootstrap_anchor": {"source": "none"},
        "families": [
            {
                "family_id": "inventory_market_maker",
                "count": 2,
                "observe_interval_ns": 100_000_000,
                "latency_ns": 5_000_000,
                "params": {
                    "leverage_tier": 1,
                    "half_spread_ticks": 5,
                    "quote_size": 10_000,
                    "max_inventory": 100_000,
                    "inventory_skew_k_bp": 10_000,
                },
            },
            {
                "family_id": "goal_belief",
                "count": 3,
                "observe_interval_ns": 1_000_000_000,
                "latency_ns": 50_000_000,
                "params": {
                    "goal_model_id": "risk_budget_linear_v1",
                    "leverage_tier": 10,
                    "risk_appetite_x1000": 2000,
                    "aggressiveness_bp": 10_000,
                    "max_order_qty": 10_000,
                    "ewma_half_life_trades": 0,
                },
            },
        ],
    }


def _synthetic_anchor() -> dict:
    return {
        "source": "synthetic",
        "quantity_units": 1,
        "direction": "family_parity",
        "pricing": "best_opposite_else_initial_limit",
    }


def _code(body: dict) -> str:
    with pytest.raises(RosterError) as exc:
        parse_roster(body)
    return exc.value.code


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #


def test_roster_id_is_stable_and_ignores_key_order() -> None:
    body = _body()
    reordered = json.loads(json.dumps(body, sort_keys=True))
    reordered["engine"] = dict(reversed(list(reordered["engine"].items())))
    assert parse_roster(body).roster_id == parse_roster(reordered).roster_id
    assert parse_roster(body).roster_id.startswith("roster-")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.__setitem__("seed", 8),
        lambda b: b["engine"].__setitem__("maint_bp", 600),
        lambda b: b.__setitem__("bootstrap_anchor", _synthetic_anchor()),
        lambda b: b["families"][0].__setitem__("count", 3),
        lambda b: b["families"][1].__setitem__("observe_interval_ns", 2_000_000_000),
        lambda b: b["families"][1]["params"].__setitem__("ewma_half_life_trades", 5),
        lambda b: b["families"].reverse(),
    ],
    ids=["seed", "engine", "anchor", "count", "timescale", "params", "family-order"],
)
def test_any_content_change_moves_the_roster_id(mutate) -> None:
    base = parse_roster(_body())
    changed = _body()
    mutate(changed)
    assert parse_roster(changed).roster_id != base.roster_id


def test_engine_digest_tracks_only_the_engine_block() -> None:
    base = parse_roster(_body())
    other_seed = _body()
    other_seed["seed"] = 99
    other_engine = _body()
    other_engine["engine"]["taker_bps"] = 6
    assert parse_roster(other_seed).engine_config_digest == base.engine_config_digest
    assert parse_roster(other_engine).engine_config_digest != base.engine_config_digest


# --------------------------------------------------------------------------- #
# Persist and rebuild from roster_id
# --------------------------------------------------------------------------- #


def test_roster_rebuilds_from_its_id(tmp_path) -> None:
    roster = parse_roster(_body())
    path = save_roster(roster, tmp_path)
    assert path.name == f"{roster.roster_id}.json"
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["roster_id"] == roster.roster_id
    assert persisted["engine_config_digest"] == roster.engine_config_digest

    rebuilt = load_roster(tmp_path, roster.roster_id)
    assert rebuilt == roster
    assert build_agent_specs(rebuilt) == build_agent_specs(roster)


def test_tampered_roster_file_is_rejected(tmp_path) -> None:
    roster = parse_roster(_body())
    path = save_roster(roster, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["families"][0]["count"] = 9  # content edited, recorded id kept
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RosterError) as exc:
        load_roster(tmp_path, roster.roster_id)
    assert exc.value.code == "ROSTER_ID_MISMATCH"


def test_stale_recorded_digest_is_rejected_even_when_content_is_intact(tmp_path) -> None:
    """The audit fields in the file must match what the content derives."""
    roster = parse_roster(_body())
    path = save_roster(roster, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["engine_config_digest"] = "0" * 32
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RosterError) as exc:
        load_roster(tmp_path, roster.roster_id)
    assert exc.value.code == "ROSTER_ID_MISMATCH"


def test_roster_file_under_a_foreign_name_is_rejected(tmp_path) -> None:
    roster = parse_roster(_body())
    path = save_roster(roster, tmp_path)
    alias = tmp_path / "roster-0000.json"
    alias.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(RosterError) as exc:
        load_roster(tmp_path, "roster-0000")
    assert exc.value.code == "ROSTER_ID_MISMATCH"


def test_missing_roster_is_rejected(tmp_path) -> None:
    with pytest.raises(RosterError) as exc:
        load_roster(tmp_path, "roster-deadbeef")
    assert exc.value.code == "ROSTER_NOT_FOUND"


# --------------------------------------------------------------------------- #
# Closed-world validation
# --------------------------------------------------------------------------- #


def test_valid_roster_is_accepted() -> None:
    roster = parse_roster(_body())
    assert [f.family_id for f in roster.families] == ["inventory_market_maker", "goal_belief"]


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda b: b.__setitem__("extra", 1), "UNKNOWN_FIELD"),
        (lambda b: b["families"][0].__setitem__("extra", 1), "UNKNOWN_FIELD"),
        (lambda b: b["families"][1]["params"].__setitem__("signal_bp", 1), "UNKNOWN_FIELD"),
        (lambda b: b["engine"].pop("mult"), "MISSING_FIELD"),
        (lambda b: b["families"][0]["params"].pop("quote_size"), "MISSING_FIELD"),
        (lambda b: b.__setitem__("schema_version", 2), "SCHEMA_VERSION_UNSUPPORTED"),
        (lambda b: b["families"][0].__setitem__("family_id", "no_such_family"), "UNKNOWN_FAMILY"),
        (lambda b: b["families"].append(copy.deepcopy(b["families"][0])), "DUPLICATE_FAMILY"),
        (lambda b: b["families"][0].__setitem__("count", 0), "INVALID_VALUE"),
        (lambda b: b["families"][0].__setitem__("count", True), "INVALID_VALUE"),
        (lambda b: b.__setitem__("families", []), "INVALID_VALUE"),
        (lambda b: b["engine"].__setitem__("mult", "1000"), "INVALID_VALUE"),
        (
            lambda b: b["families"][1]["params"].__setitem__("goal_model_id", "nope"),
            "INVALID_VALUE",
        ),
    ],
    ids=[
        "top-unknown",
        "family-unknown",
        "params-unknown",
        "engine-missing",
        "params-missing",
        "schema-version",
        "unregistered-family",
        "duplicate-family",
        "count-zero",
        "count-bool",
        "no-families",
        "engine-str",
        "unknown-goal-model",
    ],
)
def test_invalid_roster_fails_closed_with_stable_code(mutate, code) -> None:
    body = _body()
    mutate(body)
    assert _code(body) == code


# --------------------------------------------------------------------------- #
# Cold-start anchor (schema frozen here by T962, behaviour in agent/anchor.py by T963)
# --------------------------------------------------------------------------- #


def test_synthetic_anchor_schema_is_accepted() -> None:
    body = _body()
    body["bootstrap_anchor"] = _synthetic_anchor()
    assert parse_roster(body).bootstrap_anchor["source"] == "synthetic"


@pytest.mark.parametrize(
    ("anchor", "code"),
    [
        ({"source": "historical_snapshot"}, "UNKNOWN_ANCHOR_SOURCE"),
        ({"source": "none", "quantity_units": 1}, "UNKNOWN_FIELD"),
        ({**_synthetic_anchor(), "direction": "random"}, "INVALID_VALUE"),
        ({**_synthetic_anchor(), "pricing": "mid"}, "INVALID_VALUE"),
        ({**_synthetic_anchor(), "quantity_units": 0}, "INVALID_VALUE"),
        ({"source": "synthetic"}, "MISSING_FIELD"),
    ],
    ids=["adr014-not-registered", "none-extra", "random-direction", "pricing", "qty", "missing"],
)
def test_invalid_anchor_fails_closed(anchor, code) -> None:
    body = _body()
    body["bootstrap_anchor"] = anchor
    assert _code(body) == code


def test_roster_asking_for_an_anchor_never_runs_without_one(monkeypatch) -> None:
    """A schema-valid source with no registered runtime fails closed at assembly."""
    import market_game_sim.experiment.roster as roster_module

    monkeypatch.setattr(roster_module, "registered_anchor_sources", lambda: frozenset({"none"}))
    body = _body()
    body["bootstrap_anchor"] = _synthetic_anchor()
    with pytest.raises(RosterError) as exc:
        build_experiment_config(parse_roster(body), max_transactions=100)
    assert exc.value.code == "ANCHOR_SOURCE_NOT_IMPLEMENTED"


def test_anchor_on_agents_that_never_warm_up_fails_closed() -> None:
    """``ewma_half_life_trades == 0`` would make the anchor silently inert."""
    body = _body()
    body["bootstrap_anchor"] = _synthetic_anchor()
    assert body["families"][1]["params"]["ewma_half_life_trades"] == 0
    with pytest.raises(RosterError) as exc:
        build_experiment_config(parse_roster(body), max_transactions=100)
    assert exc.value.code == "ANCHOR_WITHOUT_WARMUP"


def test_synthetic_anchor_roster_assembles_and_breaks_the_deadlock() -> None:
    body = _body()
    body["bootstrap_anchor"] = _synthetic_anchor()
    body["families"][1]["params"]["ewma_half_life_trades"] = 5
    config = build_experiment_config(parse_roster(body), max_transactions=600)
    goal_ids = ["goal_belief-0", "goal_belief-1", "goal_belief-2"]
    # Only goal-model families are anchored; the market makers are not.
    assert config.bootstrap_anchor == {
        **_synthetic_anchor(),
        "families": [["goal_belief", goal_ids]],
    }

    result = run_one(config)
    assert result.bootstrap_anchor["source"] == "synthetic"
    submitted = {
        e["agent_id"]
        for e in result.events
        if e["event_type"] == "ORDER_ARRIVAL" and e.get("action") == "SUBMIT"
    }
    assert set(goal_ids) <= submitted

    # Same roster, no anchor: the same goal agents stay silent (AC-501 反向).
    body["bootstrap_anchor"] = {"source": "none"}
    silent = run_one(build_experiment_config(parse_roster(body), max_transactions=600))
    assert not {
        e["agent_id"]
        for e in silent.events
        if e["event_type"] == "ORDER_ARRIVAL" and e.get("action") == "SUBMIT"
    } & set(goal_ids)


# --------------------------------------------------------------------------- #
# Assembly: many agents across families, reproducible runs
# --------------------------------------------------------------------------- #


def test_families_expand_in_roster_order_with_family_scoped_ids() -> None:
    specs = build_agent_specs(parse_roster(_body()))
    assert [s.agent_id for s in specs] == [
        "inventory_market_maker-0",
        "inventory_market_maker-1",
        "goal_belief-0",
        "goal_belief-1",
        "goal_belief-2",
    ]
    assert all(s.is_market_maker for s in specs[:2])
    assert all(s.goal_model_id == "risk_budget_linear_v1" for s in specs[2:])
    assert {s.observe_interval_ns for s in specs[2:]} == {1_000_000_000}


def test_config_carries_the_engine_block() -> None:
    config = build_experiment_config(parse_roster(_body()), max_transactions=100)
    assert (config.seed, config.maint_bp, config.taker_bps) == (7, 500, 5)
    assert len(config.agent_specs) == 5


def test_same_roster_and_seed_reproduce_the_run(tmp_path) -> None:
    roster = parse_roster(_body())
    save_roster(roster, tmp_path)
    first = build_experiment_config(roster, max_transactions=300)
    second = build_experiment_config(load_roster(tmp_path, roster.roster_id), max_transactions=300)
    assert compute_config_hash(first) == compute_config_hash(second)

    def digest(config) -> str:
        events = run_one(config).events
        blob = json.dumps(events, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()

    run_a, run_b = digest(first), digest(second)
    assert run_a == run_b
    other_seed = _body()
    other_seed["seed"] = 8
    assert digest(build_experiment_config(parse_roster(other_seed), max_transactions=300)) != run_a
