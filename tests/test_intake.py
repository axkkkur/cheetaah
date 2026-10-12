"""Phase 2 acceptance: run_intake with injected transcript ends awaiting_approval."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db import db, init_db
from app.quotes import quote_in


FIXTURE = Path(__file__).parent / "fixtures" / "meeting1_hinglish.txt"


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cheetaah_data", str(tmp_path))
    db_path = init_db()
    yield db_path


def test_run_intake_injected_transcript(fresh_db, monkeypatch):
    transcript = FIXTURE.read_text(encoding="utf-8")

    def fake_transcribe(path):
        return transcript

    extract_payload = {
        "summary": "Team chose SQLite for MVP and tasked Rahul to update README.",
        "decisions": [
            {
                "topic": "Database",
                "decision": "Use SQLite for the MVP database.",
                "quote": "hum SQLite hi use karenge for the MVP database",
                "speaker": "Speaker 1",
            },
            {
                "topic": "Pricing",
                "decision": "Do not change pricing this quarter.",
                "quote": "Pricing change nahi karenge this quarter",
                "speaker": "Speaker 1",
            },
        ],
        "action_items": [
            {
                "title": "Update README setup",
                "owner": "Rahul",
                "due": "Friday",
                "kind": "doc_change",
                "target_paths": ["README.md"],
                "instruction": "Update README.md with install and run commands for the project.",
                "quote": "README mein setup steps update kar do",
            }
        ],
    }

    judge_payload = {"matches": []}
    calls = {"n": 0}

    def fake_claude(system, user, tool_name, schema, max_tokens=4096):
        calls["n"] += 1
        if tool_name == "extraction":
            return extract_payload
        if tool_name == "judge_result":
            return judge_payload
        raise AssertionError(tool_name)

    monkeypatch.setattr("app.pipeline.orchestrator.transcribe", fake_transcribe)
    monkeypatch.setattr("app.pipeline.extract.llm_structured", fake_claude)
    monkeypatch.setattr("app.pipeline.memory.llm_structured", fake_claude)

    from app.pipeline.orchestrator import run_intake

    audio = Path(fresh_db).parent / "audio" / "t.webm"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"fake")

    with db(fresh_db) as conn:
        cur = conn.execute(
            "INSERT INTO meetings (title, audio_path, status, created_at) VALUES (?, ?, ?, ?)",
            ("MVP sync", str(audio), "uploaded", "2026-01-01T00:00:00+00:00"),
        )
        meeting_id = cur.lastrowid

    run_intake(meeting_id)

    with db(fresh_db) as conn:
        m = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        decisions = conn.execute(
            "SELECT * FROM decisions WHERE meeting_id = ?", (meeting_id,)
        ).fetchall()
        items = conn.execute(
            "SELECT * FROM action_items WHERE meeting_id = ?", (meeting_id,)
        ).fetchall()

    assert m["status"] == "awaiting_approval"
    assert m["transcript"] == transcript
    assert len(decisions) >= 1
    assert len(items) >= 1
    for d in decisions:
        assert quote_in(d["quote"], transcript)
    for a in items:
        assert quote_in(a["quote"], transcript)
        assert json.loads(a["target_paths"]) == ["README.md"]
