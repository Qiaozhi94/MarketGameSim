"""0.4.2 T1127（SC-605 / AC-609）：功效近似、预注册文件与配对入口守卫。

规格见 docs/features/0.4/0.4.2-human-perturbation/spec.md SC-605、§6。
"""

from __future__ import annotations

import json
import math
import statistics

import pytest

from market_game_sim.experiment.perturbation import preregistration as pr
from market_game_sim.experiment.perturbation import session
from market_game_sim.metrics.stability_effect import METRIC_IDS


def _header(session_id, seed=7):
    return {
        "format_version": 1,
        "session_id": session_id,
        "arm": "human",
        "replay_mode": "original",
        "roster_id": "roster-" + "e" * 32,
        "seed": seed,
        "engine_config_digest": "a" * 32,
        "evidence_class": "experiment-preview",
        "run_mode": "interactive",
    }


def _sessions(directory):
    directory.mkdir()
    sealed = session.SessionWriter.create(directory / "a.jsonl", _header("s-a"))
    sealed.append_action(
        advance_index=3,
        kind="MARKET",
        payload={"side": "BUY", "quantity_units": 1},
        wall_clock_ms=1,
    )
    sealed.seal(end_advance_index=9, event_digest="d" * 64, observation_digests=[])
    unsealed = session.SessionWriter.create(directory / "b.jsonl", _header("s-b"))
    unsealed.append_action(
        advance_index=4,
        kind="MARKET",
        payload={"side": "SELL", "quantity_units": 2},
        wall_clock_ms=1,
    )
    unsealed.close()
    return directory


def _points():
    points = []
    for i, seed in enumerate(pr.POWER_SEEDS):
        metrics = {m: 0.1 + 0.01 * i + 0.001 * k for k, m in enumerate(METRIC_IDS)}
        points.append({"seed": seed, "degenerate": [], "metrics": metrics})
    points[0] = {**points[0], "degenerate": ["NO_TRADES_IN_WINDOW"], "metrics": None}
    return points


def test_required_n_is_the_conservative_paired_approximation():
    sigma, mde = 0.02, 0.01
    expected = math.ceil(((pr.Z_95 + pr.Z_80) * math.sqrt(2) * sigma / mde) ** 2)
    assert pr.required_n(sigma, mde) == expected == 50
    assert pr.required_n(0.0, 0.01) == 1
    with pytest.raises(pr.PreregistrationError):
        pr.required_n(0.02, 0)


def test_power_report_uses_valid_seeds_only():
    report = pr.power_report(_points())
    assert report["valid_seeds"] == len(pr.POWER_SEEDS) - 1
    valid = _points()[1:]
    for metric in METRIC_IDS:
        expected = statistics.stdev(p["metrics"][metric] for p in valid)
        assert report["sigma_b"][metric] == pytest.approx(expected)
        assert report["power"]["n_by_mde_in_sigma_b"][metric]["1.0"] == pr.required_n(1, 1)
    assert report["per_seed"][0]["degenerate"] == ["NO_TRADES_IN_WINDOW"], "退化种子如实列出"
    assert report["evidence_class"] == "experiment-preview"
    assert set(pr.POWER_SEEDS).isdisjoint({7}) and len(pr.POWER_SEEDS) == 20


def test_every_existing_session_is_collected_and_none_can_be_left_out(tmp_path):
    sessions = pr.collect_sessions(_sessions(tmp_path / "sessions"))
    assert [(s["session_id"], s["status"]) for s in sessions] == [
        ("s-a", session.SEALED),
        ("s-b", session.UNSEALED),
    ]
    (tmp_path / "sessions" / "c.jsonl").write_text("not a session\n")
    with pytest.raises(pr.PreregistrationError) as exc:
        pr.collect_sessions(tmp_path / "sessions")
    assert exc.value.code == pr.PREREGISTRATION_INVALID, "不合格的会话不能被悄悄略过"
    (tmp_path / "empty").mkdir()
    with pytest.raises(pr.PreregistrationError):
        pr.collect_sessions(tmp_path / "empty")


def _mde():
    return {m: 0.05 for m in METRIC_IDS}


def _built(tmp_path, **overrides):
    power = pr.power_report(_points())
    sessions = pr.collect_sessions(_sessions(tmp_path / "sessions"))
    kwargs = {"open_loop_seeds": list(range(2001, 2031)), **overrides}
    return power, pr.build_preregistration(power, "f" * 64, sessions, _mde(), **kwargs)


def test_preregistration_rules(tmp_path):
    power, built = _built(tmp_path)
    assert built["n_required"] == max(built["n_by_metric"].values())
    assert built["min_valid_pairs"] == built["n_required"]
    assert len(built["treatment_sessions"]) == 2
    assert built["statistics"]["ci_level"] == 0.90
    sessions = built["treatment_sessions"]
    for bad_seeds in ([7, *range(2001, 2030)], [1001, *range(2001, 2030)], [2001, 2001]):
        with pytest.raises(pr.PreregistrationError):
            pr.build_preregistration(power, "f" * 64, sessions, _mde(), open_loop_seeds=bad_seeds)
    with pytest.raises(pr.PreregistrationError):
        pr.build_preregistration(
            power, "f" * 64, sessions, _mde(), open_loop_seeds=[2001, 2002], min_valid_pairs=3
        )
    with pytest.raises(pr.PreregistrationError):
        pr.build_preregistration(
            power, "f" * 64, sessions, {METRIC_IDS[0]: 0.1}, open_loop_seeds=[2001]
        )


def _files(tmp_path):
    power, _ = _built(tmp_path)
    power_path = tmp_path / "power.json"
    power_path.write_text(json.dumps(power))
    sessions = pr.collect_sessions(tmp_path / "sessions")
    built = pr.build_preregistration(
        power, pr.file_sha256(power_path), sessions, _mde(), open_loop_seeds=list(range(2001, 2031))
    )
    prereg_path = tmp_path / "prereg.json"
    prereg_path.write_text(json.dumps(built))
    return power_path, prereg_path


def test_pairing_refuses_missing_tampered_or_unlisted_treatment(tmp_path):
    """AC-609：
    预注册文件缺失、哈希不一致或处理会话不在其中时配对入口 fail closed，一致时放行（正反两侧）
    """
    power_path, prereg_path = _files(tmp_path)
    sha = pr.file_sha256(prereg_path)
    kwargs = {"pinned_sha256": sha, "power_report_path": power_path}

    prereg, recorded = pr.begin_pairing(prereg_path, **kwargs)
    assert recorded == sha
    listed = session.load_session(tmp_path / "sessions" / "a.jsonl")
    assert pr.require_treatment(prereg, listed)["session_id"] == "s-a"
    pr.verify_preregistration(recorded, prereg_path)

    def code(**changes):
        with pytest.raises(pr.PreregistrationError) as exc:
            pr.begin_pairing(changes.pop("path", prereg_path), **{**kwargs, **changes})
        return exc.value.code

    assert code(path=tmp_path / "absent.json") == pr.PREREGISTRATION_MISSING
    assert code(pinned_sha256="0" * 64) == pr.PREREGISTRATION_DRIFT

    original = prereg_path.read_text()
    prereg_path.write_text(original.replace('"min_valid_pairs": ', '"min_valid_pairs": 1', 1))
    assert code() == pr.PREREGISTRATION_DRIFT
    with pytest.raises(pr.PreregistrationError) as exc:
        pr.verify_preregistration(recorded, prereg_path)
    assert exc.value.code == pr.PREREGISTRATION_DRIFT
    prereg_path.write_text(original)

    power_path.write_text(power_path.read_text() + " ")
    assert code() == pr.POWER_REPORT_DRIFT

    extra = session.SessionWriter.create(tmp_path / "late.jsonl", _header("s-late"))
    extra.close()
    with pytest.raises(pr.PreregistrationError) as exc:
        pr.require_treatment(prereg, session.load_session(tmp_path / "late.jsonl"))
    assert exc.value.code == pr.TREATMENT_NOT_PREREGISTERED


def test_repository_state_cannot_pair_before_preregistration():
    """仓库现状：没有钉住的预注册就不能跑正式配对；钉住了则必须与文件一致。"""
    if pr.PREREGISTRATION_SHA256 is None:
        with pytest.raises(pr.PreregistrationError) as exc:
            pr.begin_pairing()
        assert exc.value.code in {pr.PREREGISTRATION_MISSING, pr.PREREGISTRATION_NOT_PINNED}
    else:
        assert pr.file_sha256(pr.PREREGISTRATION_PATH) == pr.PREREGISTRATION_SHA256
        assert pr.begin_pairing()[1] == pr.PREREGISTRATION_SHA256


def test_unpinned_preregistration_is_refused(tmp_path, monkeypatch):
    power_path, prereg_path = _files(tmp_path)
    monkeypatch.setattr(pr, "PREREGISTRATION_SHA256", None)
    with pytest.raises(pr.PreregistrationError) as exc:
        pr.begin_pairing(prereg_path, power_report_path=power_path)
    assert exc.value.code == pr.PREREGISTRATION_NOT_PINNED


def test_cli_never_rewrites_a_preregistration(tmp_path):
    power_path, prereg_path = _files(tmp_path)
    args = ["preregister", "--sessions-dir", str(tmp_path / "sessions"), "--mde", "0.05", "0.05"]
    args += ["0.05", "0.05", "--open-loop-seeds", *map(str, range(2001, 2031))]
    args += ["--power-report", str(power_path), "--out", str(prereg_path)]
    before = prereg_path.read_bytes()
    assert pr.main(args) == 2
    assert prereg_path.read_bytes() == before
    fresh = tmp_path / "fresh.json"
    assert pr.main(args[:-1] + [str(fresh)]) == 0
    assert json.loads(fresh.read_text())["power_report_sha256"] == pr.file_sha256(power_path)


def test_cli_power_writes_the_report(tmp_path, monkeypatch):
    """CLI power：跑逐种子基线（此处以桩代替全窗口运行）并写出功效报告。"""
    calls = []

    def fake(seeds=pr.POWER_SEEDS, *, jobs=1, cache_dir=None):
        calls.append((tuple(seeds), jobs, cache_dir))
        return _points()

    monkeypatch.setattr(pr, "run_power_baseline", fake)
    out = tmp_path / "power.json"
    cache = tmp_path / "cache"
    assert pr.main(["power", "--jobs", "1", "--out", str(out), "--cache-dir", str(cache)]) == 0
    assert calls == [(pr.POWER_SEEDS, 1, cache)]
    assert json.loads(out.read_text()) == json.loads(json.dumps(pr.power_report(_points())))


def test_power_baseline_resumes_from_its_cache(tmp_path, monkeypatch):
    """被中断后续跑：已落盘的种子不重跑；清单标识对不上的缓存作废重跑；结果原子落盘。"""
    from market_game_sim.experiment.perturbation import carrier

    ran = []

    def fake_point(seed):
        ran.append(seed)
        return {"seed": seed, "roster_id": carrier.carrier_roster(seed).roster_id, "degenerate": []}

    monkeypatch.setattr(pr, "_baseline_point", fake_point)
    seeds = (1001, 1002)
    first = pr.run_power_baseline(seeds, cache_dir=tmp_path)
    assert ran == [1001, 1002] and sorted(p.name for p in tmp_path.iterdir()) == [
        "seed-1001.json",
        "seed-1002.json",
    ]
    assert pr.run_power_baseline(seeds, cache_dir=tmp_path) == first
    assert ran == [1001, 1002], "缓存命中不重跑"

    stale = json.loads((tmp_path / "seed-1002.json").read_text())
    (tmp_path / "seed-1002.json").write_text(json.dumps({**stale, "roster_id": "roster-old"}))
    pr.run_power_baseline(seeds, cache_dir=tmp_path)
    assert ran == [1001, 1002, 1002], "清单变了的缓存不可复用"
    pr.run_power_baseline(seeds)
    assert ran[-2:] == [1001, 1002], "不给缓存目录时照常全跑"
