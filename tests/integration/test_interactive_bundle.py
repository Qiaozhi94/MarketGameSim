"""T813: same-source, content-addressed interactive delivery bundle."""

import hashlib
import json

from market_game_sim.interactive.bundle import validate_interactive_manifest
from market_game_sim.interactive.delivery import generate_interactive_delivery
from market_game_sim.interactive.journal import read_input_journal
from market_game_sim.replay.reader import read_log


def test_interactive_bundle_manifest_contract(tmp_path) -> None:
    out = tmp_path / "H1"
    generated = generate_interactive_delivery(out)
    assert set(generated) == {
        "run_doc",
        "input_journal",
        "event_log",
        "replay",
        "manifest",
    }
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    validate_interactive_manifest(manifest, out)
    assert manifest["run_mode"] == "interactive"
    assert manifest["evidence_class"] == "engineering-demonstration"
    journal = read_input_journal(out / "input-journal.jsonl")
    assert manifest["session_id"] == journal.session_id == read_log(out / "run.jsonl").run_id
    for entry in manifest["artifacts"]:
        digest = hashlib.sha256((out / entry["path"]).read_bytes()).hexdigest()
        assert digest == entry["sha256"]


def test_bundle_refuses_overwrite(tmp_path) -> None:
    out = tmp_path / "H1"
    generate_interactive_delivery(out)
    try:
        generate_interactive_delivery(out)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing bundle must not be overwritten")
