"""T815 H1-C gate: representative bundle from one public command."""

import json
import subprocess
import sys


def test_single_command_delivers_replayable_h1_bundle(tmp_path) -> None:
    out = tmp_path / "H1"
    completed = subprocess.run(
        [sys.executable, "-m", "market_game_sim.interactive.delivery", "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert {item.name for item in out.iterdir()} == {
        "RUN.md",
        "manifest.json",
        "input-journal.jsonl",
        "run.jsonl",
        "replay.html",
    }
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["termination_state"] == "COMPLETED"
    assert manifest["run_mode"] == "interactive"
    replay = subprocess.run(
        [
            sys.executable,
            "-m",
            "market_game_sim.interactive.replay_session",
            str(out / "input-journal.jsonl"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert replay.returncode == 0, replay.stderr
    replay_result = json.loads(replay.stdout)
    assert replay_result["input_hash"] == manifest["input_hash"]
    assert replay_result["frame_hash"] == manifest["frame_hash"]
