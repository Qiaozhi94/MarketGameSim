"""0.4.2 PerturbationSession：T1120 冻结格式、T1122 落盘与校验、T1123 判定/画像/身份字段拒绝
（AC-601、AC-602、AC-606）。规格见 docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import hashlib
import json
import shutil
import subprocess
import sys

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


# --------------------------------------------------------------------------- #
# T1122：落盘、封口、读取与校验
# --------------------------------------------------------------------------- #

_DIGEST = "d" * 64


def _actions():
    return [
        _action(1, 3, side="BUY", quantity_units=5, price_ticks=9_990),
        _action(2, 3, side="SELL", quantity_units=2),
        _action(3, 8, target_action_seq=1),
        _action(4, 8, target_action_seq=1),
    ]


def _seal(header, actions, **overrides):
    seal = {
        "record_type": "seal",
        "end_advance_index": 12,
        "event_digest": _DIGEST,
        "observation_digests": [
            {"action_seq": a["action_seq"], "digest": _DIGEST} for a in actions
        ],
        "content_hash": session.content_hash(header, actions),
    }
    seal.update(overrides)
    return seal


def _file(records):
    return b"".join(session.record_line(r) for r in records)


def _write_session(path, actions, *, seal=True):
    header = {k: v for k, v in _header().items() if k != "record_type"}
    writer = session.SessionWriter.create(path, header)
    for action in actions:
        written = writer.append_action(
            advance_index=action["advance_index"],
            kind=action["kind"],
            payload=action["payload"],
            wall_clock_ms=action["wall_clock_ms"],
        )
        assert written == action
    if seal:
        writer.seal(
            end_advance_index=12,
            event_digest=_DIGEST,
            observation_digests=[
                {"action_seq": a["action_seq"], "digest": _DIGEST} for a in actions
            ],
        )
    return writer


@pytest.mark.parametrize("actions", [[], _actions()], ids=["empty", "multi_action"])
def test_session_artifact_frozen_format_round_trips_and_rejects_invalid(tmp_path, actions):
    """AC-601：按冻结格式落盘、读回逐字段相同、封口哈希与重算一致；文件即规范行拼接。"""
    path = tmp_path / "session.jsonl"
    writer = _write_session(path, actions)
    assert writer.sealed
    check = session.load_session(path)
    assert check.ok, check
    assert check.status == session.SEALED and not check.truncated_tail
    assert check.header == _header()
    assert list(check.actions) == actions
    assert check.seal == _seal(_header(), actions)
    assert check.content_hash == check.seal["content_hash"] == writer.content_hash
    assert path.read_bytes() == _file([_header(), *actions, _seal(_header(), actions)])


def _drop(record, key):
    return {k: v for k, v in record.items() if k != key}


def _with(record, **changes):
    return {**record, **changes}


def _invalid_cases():
    h, a = _header(), _actions()
    ok_seal = _seal(h, a)
    gap = [*a[:1], _with(a[1], action_seq=3)]
    back = [*a[:1], _with(a[1], advance_index=2)]
    on_market = [*a[:2], _with(a[2], payload={"target_action_seq": 2})]
    ahead = [*a[:2], _with(a[2], payload={"target_action_seq": 4})]
    return {
        "empty_file": (b"", "MISSING_HEADER"),
        "first_line_not_header": (_file([a[0]]), "MISSING_HEADER"),
        "header_missing_seed": (_file([_drop(h, "seed")]), "MISSING_FIELD"),
        "header_missing_version": (_file([_drop(h, "format_version")]), "MISSING_FIELD"),
        "wrong_version": (_file([_with(h, format_version=2)]), "UNSUPPORTED_VERSION"),
        "header_bad_roster_id": (_file([_with(h, roster_id="roster-x")]), "INVALID_VALUE"),
        "action_unknown_field": (_file([h, _with(a[0], note="x")]), "UNKNOWN_FIELD"),
        "payload_unknown_field": (
            _file([h, _with(a[1], payload={**a[1]["payload"], "price_ticks": 1})]),
            "UNKNOWN_FIELD",
        ),
        "payload_missing_field": (
            _file([h, _with(a[0], payload=_drop(a[0]["payload"], "price_ticks"))]),
            "MISSING_FIELD",
        ),
        "quantity_over_cap": (
            _file([h, _with(a[1], payload={"side": "BUY", "quantity_units": 1001})]),
            "INVALID_VALUE",
        ),
        "bool_as_integer": (_file([h, _with(a[0], advance_index=True)]), "INVALID_VALUE"),
        "unknown_record_type": (_file([h, _with(a[0], record_type="note")]), "INVALID_VALUE"),
        "non_canonical_line": (
            _file([h]) + json.dumps(a[0], indent=1).replace("\n", " ").encode() + b"\n",
            "NON_CANONICAL_RECORD",
        ),
        "float_value": (
            _file([h])
            + json.dumps(
                _with(a[1], wall_clock_ms=1.5), sort_keys=True, separators=(",", ":")
            ).encode()
            + b"\n",
            "NON_CANONICAL_RECORD",
        ),
        "blank_line": (_file([h]) + b"\n", "NON_CANONICAL_RECORD"),
        "duplicate_header": (_file([h, h]), "OUT_OF_ORDER"),
        "record_after_seal": (_file([h, *a, ok_seal, a[0]]), "OUT_OF_ORDER"),
        "seq_gap": (_file([h, *gap]), "INVALID_SEQUENCE"),
        "advance_regress": (_file([h, *back]), "INVALID_SEQUENCE"),
        "cancel_targets_market": (_file([h, *on_market]), "INVALID_SEQUENCE"),
        "cancel_targets_later": (_file([h, *ahead]), "INVALID_SEQUENCE"),
        "seal_before_last_action": (
            _file([h, *a, _seal(h, a, end_advance_index=7)]),
            "INVALID_SEQUENCE",
        ),
        "observation_seq_unknown": (
            _file([h, *a, _seal(h, a, observation_digests=[{"action_seq": 5, "digest": _DIGEST}])]),
            "INVALID_SEQUENCE",
        ),
        "observation_seq_not_increasing": (
            _file(
                [
                    h,
                    *a,
                    _seal(
                        h,
                        a,
                        observation_digests=[
                            {"action_seq": 2, "digest": _DIGEST},
                            {"action_seq": 2, "digest": _DIGEST},
                        ],
                    ),
                ]
            ),
            "INVALID_SEQUENCE",
        ),
        "seal_hash_tampered": (
            _file([h, *a, _seal(h, a, content_hash="0" * 64)]),
            "CONTENT_HASH_MISMATCH",
        ),
        "action_tampered_after_seal": (
            _file([h, *a[:3], _with(a[3], wall_clock_ms=1), ok_seal]),
            "CONTENT_HASH_MISMATCH",
        ),
    }


_INVALID = _invalid_cases()


@pytest.mark.parametrize("case", sorted(_INVALID))
def test_invalid_session_files_get_stable_reason_codes(case):
    """AC-601 反例：每类非法输入给冻结记录里的稳定原因码，不抛异常。"""
    data, code = _INVALID[case]
    check = session.validate_session(data)
    assert not check.ok and check.reason_code == code, (case, check)
    assert check.reason_code in session.load_format()["reason_codes"]


def test_every_frozen_reason_code_has_a_negative_case():
    """反例覆盖冻结记录里的全部原因码（FORBIDDEN_FIELD 由 AC-606 用例覆盖）。"""
    covered = {code for _, code in _INVALID.values()} | {"FORBIDDEN_FIELD"}
    assert covered == set(session.load_format()["reason_codes"])


def test_writer_refuses_invalid_records_without_writing(tmp_path):
    """写入侧 fail closed：不合格的动作一个字节都不写；已存在的文件不被覆盖；封口后不再追加。"""
    path = tmp_path / "session.jsonl"
    writer = _write_session(path, _actions()[:1], seal=False)
    before = path.read_bytes()
    with pytest.raises(session.SessionError) as exc:
        writer.append_action(
            advance_index=4,
            kind="MARKET",
            payload={"side": "BUY", "quantity_units": 0},
            wall_clock_ms=1,
        )
    assert exc.value.code == "INVALID_VALUE"
    with pytest.raises(session.SessionError) as exc:
        writer.append_action(
            advance_index=4, kind="CANCEL", payload={"target_action_seq": 9}, wall_clock_ms=1
        )
    assert exc.value.code == "INVALID_SEQUENCE"
    assert path.read_bytes() == before
    second = writer.append_action(
        advance_index=4,
        kind="MARKET",
        payload={"side": "SELL", "quantity_units": 1},
        wall_clock_ms=1,
    )
    assert second["action_seq"] == 2, "被拒的动作不占用序号"

    with pytest.raises(FileExistsError):
        session.SessionWriter.create(path, _drop(_header(), "record_type"))

    writer.seal(end_advance_index=4, event_digest=_DIGEST, observation_digests=[])
    sealed = path.read_bytes()
    with pytest.raises(session.SessionError) as exc:
        writer.append_action(
            advance_index=5,
            kind="MARKET",
            payload={"side": "BUY", "quantity_units": 1},
            wall_clock_ms=1,
        )
    assert exc.value.code == "OUT_OF_ORDER"
    assert path.read_bytes() == sealed
    assert session.load_session(path).status == session.SEALED


_KILL_SCRIPT = """
import json, os, sys
from market_game_sim.experiment.perturbation import session
path, header, actions = sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3])
writer = session.SessionWriter.create(path, header)
for a in actions:
    writer.append_action(advance_index=a["advance_index"], kind=a["kind"],
                         payload=a["payload"], wall_clock_ms=a["wall_clock_ms"])
os._exit(9)  # 不 close、不封口、不走解释器退出清理：模拟进程被杀
"""


@pytest.mark.parametrize("kept", [0, 1, 4], ids=["header_only", "one_action", "all_actions"])
def test_action_journal_survives_termination_as_unsealed(tmp_path, kept):
    """AC-602：
    头记录先于动作落盘；任意动作后终止进程不丢已取出动作、标 UNSEALED，
    未封口会话可校验、内容哈希稳定、种子与 roster_id 可读；
    空会话、多动作封口会话、未封口会话三种场景（后两者另见 round-trip 用例）
    """
    path = tmp_path / "session.jsonl"
    actions = _actions()[:kept]
    header = _drop(_header(), "record_type")
    proc = subprocess.run(
        [sys.executable, "-c", _KILL_SCRIPT, str(path), json.dumps(header), json.dumps(actions)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 9, proc.stderr
    check = session.load_session(path)
    assert check.ok, check
    assert check.status == session.UNSEALED and check.seal is None
    assert list(check.actions) == actions
    assert check.header["seed"] == 7 and check.header["roster_id"] == _header()["roster_id"]
    assert check.content_hash == session.content_hash(_header(), actions)
    assert session.load_session(path).content_hash == check.content_hash


def test_unterminated_tail_is_excluded_and_reported(tmp_path):
    """写入中途被终止留下的半行：未封口会话排除残片并报告；封口之后出现残片即拒绝。"""
    h, a = _header(), _actions()
    partial = session.record_line(a[3])[:-7]
    unsealed = session.validate_session(_file([h, *a[:3]]) + partial)
    assert unsealed.ok and unsealed.truncated_tail and unsealed.status == session.UNSEALED
    assert list(unsealed.actions) == a[:3]
    assert unsealed.content_hash == session.content_hash(h, a[:3])

    assert not session.validate_session(_file([h, *a[:3]])).truncated_tail
    after_seal = session.validate_session(_file([h, *a, _seal(h, a)]) + b'{"record')
    assert not after_seal.ok and after_seal.reason_code == "OUT_OF_ORDER"
    header_fragment = session.validate_session(session.record_line(h)[:-3])
    assert not header_fragment.ok and header_fragment.reason_code == "MISSING_HEADER"


# --------------------------------------------------------------------------- #
# T1123：对错判定、行为画像与直接身份信息
# --------------------------------------------------------------------------- #

_FORBIDDEN = session.load_format()["forbidden_fields"]["keys"]


@pytest.mark.parametrize("key", _FORBIDDEN)
def test_judgement_profile_and_identity_fields_are_rejected(key):
    """AC-606：含对错判定/画像字段与直接身份信息的产物被拒，合法 artifact 不被误拒（正反两侧）"""
    h, a = _header(), _actions()
    variants = {
        "header": _file([_with(h, **{key: "x"})]),
        "action": _file([h, _with(a[1], **{key: "x"})]),
        "payload": _file([h, _with(a[1], payload={**a[1]["payload"], key: 1})]),
        "seal": _file([h, *a, _with(_seal(h, a), **{key: "x"})]),
        "nested": _file(
            [h, *a, _seal(h, a, observation_digests=[{"action_seq": 1, "digest": _DIGEST, key: 1}])]
        ),
        "upper_case": _file([_with(h, **{key.upper(): "x"})]),
    }
    for where, data in variants.items():
        check = session.validate_session(data)
        assert not check.ok and check.reason_code == "FORBIDDEN_FIELD", (key, where, check)


def test_legal_artifacts_are_not_rejected_as_identifying():
    """AC-606 正例：合法会话（含取值里出现 name/profile 等字样）不被误拒；写入侧同样拒绝禁用键。"""
    h = _with(_header(), session_id="profile-name-score-7")
    a = _actions()
    check = session.validate_session(_file([h, *a, _seal(h, a)]))
    assert check.ok and check.status == session.SEALED
    with pytest.raises(session.SessionError) as exc:
        session.SessionWriter.create(
            "/nonexistent/never-written.jsonl", {**_drop(h, "record_type"), "email": "x"}
        )
    assert exc.value.code == "FORBIDDEN_FIELD"
