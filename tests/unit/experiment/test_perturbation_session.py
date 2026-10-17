"""0.4.2 PerturbationSession：T1120 冻结格式；T1122/T1123 skeleton（AC-601、AC-602、AC-606）。

strict-xfail 骨架：对应任务实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import hashlib
import json
import shutil

import pytest

from market_game_sim.config.serialization import SerializationError
from market_game_sim.experiment.perturbation import session

# --------------------------------------------------------------------------- #
# T1120：格式冻结
# --------------------------------------------------------------------------- #


def test_frozen_format_loads_against_its_pin():
    """AC-601：冻结格式记录按登记摘要读取，自报版本与当前写入版本一致。"""
    record = session.load_format()
    assert record["format_version"] == session.FORMAT_VERSION == 1
    assert record["status"] == "FROZEN"
    assert session.FORMAT_VERSION in session.FROZEN_FORMATS
    assert record["records"]["header"]["fields"]["format_version"]["enum"] == [1]


def test_format_change_without_new_version_is_rejected(tmp_path, monkeypatch):
    """AC-601：改动格式文件而不新建版本 → FORMAT_DRIFT；未登记版本 → UNSUPPORTED_VERSION；
    新登记但文件自报版本不符 → FORMAT_VERSION_MISMATCH。"""
    drifted = tmp_path / "format.json"
    text = session.FORMAT_PATH.read_text(encoding="utf-8")
    drifted.write_text(text.replace('"maximum": 1000', '"maximum": 1001', 1), encoding="utf-8")
    with pytest.raises(session.SessionFormatError) as exc:
        session.load_format(1, drifted)
    assert exc.value.code == "FORMAT_DRIFT"

    with pytest.raises(session.SessionFormatError) as exc:
        session.load_format(2)
    assert exc.value.code == "UNSUPPORTED_VERSION"

    copied = tmp_path / "copied.json"
    shutil.copyfile(session.FORMAT_PATH, copied)
    digest = hashlib.sha256(copied.read_bytes()).hexdigest()
    monkeypatch.setattr(session, "FROZEN_FORMATS", {1: digest, 2: digest})
    assert session.load_format(1, copied)["format_version"] == 1
    with pytest.raises(session.SessionFormatError) as exc:
        session.load_format(2, copied)
    assert exc.value.code == "FORMAT_VERSION_MISMATCH"


def test_frozen_format_covers_fr601_and_records_no_derived_ids():
    """AC-601：头记录、动作行、封口行覆盖 FR-601 / DR-601 的字段；内核派生的标识不进动作行。"""
    records = session.load_format()["records"]
    header = set(records["header"]["fields"])
    assert header == {
        "record_type",
        "format_version",
        "session_id",
        "arm",
        "replay_mode",
        "roster_id",
        "seed",
        "engine_config_digest",
        "evidence_class",
        "run_mode",
    }
    assert records["header"]["fields"]["arm"]["enum"] == ["baseline", "human"]
    assert records["header"]["fields"]["replay_mode"]["enum"] == [
        "original",
        "same_seed_replay",
        "open_loop_replay",
    ]
    action = records["action"]
    assert set(action["fields"]) == {
        "record_type",
        "advance_index",
        "action_seq",
        "kind",
        "payload",
        "wall_clock_ms",
    }
    assert set(action["payload_by_kind"]) == {"MARKET", "LIMIT", "CANCEL"}
    assert set(action["payload_by_kind"]["CANCEL"]) == {"target_action_seq"}
    derived = set(action["derived_not_recorded"])
    assert derived == {"order_id", "timestamp", "submitted_at", "decision_event_id"}
    recorded = set(action["fields"]).union(*map(set, action["payload_by_kind"].values()))
    assert not derived & recorded
    assert set(records["seal"]["fields"]) == {
        "record_type",
        "end_advance_index",
        "event_digest",
        "observation_digests",
        "content_hash",
    }


def test_forbidden_keys_never_collide_with_format_fields():
    """AC-606 的格式侧前提：禁用键与任何合法字段不重名，否则合法 artifact 会被误拒。"""
    record = session.load_format()
    records = record["records"]
    legal = set()
    for kind in ("header", "action", "seal"):
        legal |= set(records[kind]["fields"])
    for payload in records["action"]["payload_by_kind"].values():
        legal |= set(payload)
    legal |= set(records["seal"]["observation_digest"])
    forbidden = set(record["forbidden_fields"]["keys"])
    assert forbidden and not forbidden & legal
    assert {"FORBIDDEN_FIELD", "UNKNOWN_FIELD", "MISSING_FIELD", "UNSUPPORTED_VERSION"} <= set(
        record["reason_codes"]
    )


def _header():
    return {
        "record_type": "header",
        "format_version": 1,
        "session_id": "s7-original-1",
        "arm": "human",
        "replay_mode": "original",
        "roster_id": "roster-" + "0" * 32,
        "seed": 7,
        "engine_config_digest": "a" * 32,
        "evidence_class": "experiment-preview",
        "run_mode": "interactive",
    }


def _action(seq, advance, **payload):
    kind = (
        "CANCEL"
        if "target_action_seq" in payload
        else ("LIMIT" if "price_ticks" in payload else "MARKET")
    )
    return {
        "record_type": "action",
        "advance_index": advance,
        "action_seq": seq,
        "kind": kind,
        "payload": payload,
        "wall_clock_ms": 1_760_000_000_000 + seq,
    }


def test_content_hash_is_over_canonical_header_and_action_lines():
    """AC-601/AC-602：内容哈希 = 头记录与动作行规范行字节的 sha256；空会话可算，
    每条动作都影响哈希，键序不影响哈希，浮点数被拒。"""
    header = _header()
    actions = [
        _action(1, 3, side="BUY", quantity_units=5, price_ticks=9_990),
        _action(2, 3, side="SELL", quantity_units=2),
        _action(3, 8, target_action_seq=1),
    ]
    expected = hashlib.sha256(
        b"".join(
            json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            + b"\n"
            for r in [header, *actions]
        )
    ).hexdigest()
    assert session.content_hash(header, actions) == expected
    assert session.content_hash(dict(reversed(header.items())), actions) == expected

    empty = session.content_hash(header, [])
    assert empty == hashlib.sha256(session.record_line(header)).hexdigest()
    assert empty != expected

    moved = [dict(a) for a in actions]
    moved[2]["advance_index"] = 9
    assert session.content_hash(header, moved) != expected

    with pytest.raises(SerializationError):
        session.content_hash(header, [_action(1, 0, side="BUY", quantity_units=1.0)])


@pytest.mark.xfail(strict=True, reason="T1122 not implemented yet")
def test_session_artifact_frozen_format_round_trips_and_rejects_invalid():
    """AC-601：按冻结格式落盘可重放；缺字段/错版本号被校验入口拒绝（正反两侧）"""
    pytest.fail("T1122 pending")


@pytest.mark.xfail(strict=True, reason="T1122 not implemented yet")
def test_action_journal_survives_termination_as_unsealed():
    """AC-602：
    头记录先于动作落盘；任意动作后终止进程不丢已取出动作、标 UNSEALED，
    未封口会话可校验、内容哈希稳定、种子与 roster_id 可读；
    空会话、多动作封口会话、未封口会话三种场景
    """
    pytest.fail("T1122 pending")


@pytest.mark.xfail(strict=True, reason="T1123 not implemented yet")
def test_judgement_profile_and_identity_fields_are_rejected():
    """AC-606：含对错判定/画像字段与直接身份信息的产物被拒，合法 artifact 不被误拒（正反两侧）"""
    pytest.fail("T1123 pending")
