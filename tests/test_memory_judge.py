from __future__ import annotations

from pathlib import Path

import pytest

from app.db import db, init_db, now
from app.pipeline.memory import check_memory

T1 = (Path(__file__).parent / "fixtures" / "meeting1_hinglish.txt").read_text(encoding="utf-8")
T2 = (Path(__file__).parent / "fixtures" / "meeting2_reversal.txt").read_text(encoding="utf-8")


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cheetaah_data", str(tmp_path))
    init_db()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO meetings (title, transcript, status, created_at) VALUES (?, ?, ?, ?)",
            ("m1", T1, "awaiting_approval", "2026-01-01T00:00:00+00:00"),
        )
        m1 = cur.lastrowid
        cur = conn.execute(
            """
            INSERT INTO decisions (meeting_id, topic, decision, quote, speaker, decided_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                m1,
                "Database",
                "Use SQLite for the MVP database.",
                "hum SQLite hi use karenge for the MVP database",
                "Speaker 1",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        prior_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO meetings (title, transcript, status, created_at) VALUES (?, ?, ?, ?)",
            ("m2", T2, "extracting", now()),
        )
        m2 = cur.lastrowid
        cur = conn.execute(
            """
            INSERT INTO decisions (meeting_id, topic, decision, quote, speaker, decided_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                m2,
                "Database",
                "Use Postgres for the MVP instead of SQLite.",
                "SQLite nahi, ab hum Postgres use karenge for the MVP",
                "Speaker 1",
                now(),
            ),
        )
        new_id = cur.lastrowid
    return {"m2": m2, "prior_id": prior_id, "new_id": new_id}


def test_fake_judge_quote_rejected(seeded, monkeypatch):
    def fake(system, user, tool_name, schema, max_tokens=4096):
        return {
            "matches": [
                {
                    "prior_id": seeded["prior_id"],
                    "relation": "reversal",
                    "confidence": 0.95,
                    "explanation": "Switched DB",
                    "new_quote": "this quote was never said in the meeting ever",
                    "prior_quote": "hum SQLite hi use karenge for the MVP database",
                }
            ]
        }

    monkeypatch.setattr("app.pipeline.memory.llm_structured", fake)
    check_memory(seeded["m2"], T2)
    with db() as conn:
        revs = conn.execute("SELECT * FROM reversals").fetchall()
        rejected = conn.execute(
            "SELECT * FROM audit WHERE event='judge_quote_rejected'"
        ).fetchall()
    assert len(revs) == 0
    assert len(rejected) >= 1


def test_valid_reversal_stored(seeded, monkeypatch):
    def fake(system, user, tool_name, schema, max_tokens=4096):
        return {
            "matches": [
                {
                    "prior_id": seeded["prior_id"],
                    "relation": "reversal",
                    "confidence": 0.92,
                    "explanation": "Chose Postgres instead of SQLite",
                    "new_quote": "SQLite nahi, ab hum Postgres use karenge for the MVP",
                    "prior_quote": "hum SQLite hi use karenge for the MVP database",
                }
            ]
        }

    monkeypatch.setattr("app.pipeline.memory.llm_structured", fake)
    check_memory(seeded["m2"], T2)
    with db() as conn:
        rev = conn.execute("SELECT * FROM reversals").fetchone()
        prior = conn.execute(
            "SELECT decided_at FROM decisions WHERE id = ?", (seeded["prior_id"],)
        ).fetchone()
    assert rev is not None
    assert rev["relation"] == "reversal"
    assert rev["prior_decision_id"] == seeded["prior_id"]
    assert prior["decided_at"] == "2026-01-01T00:00:00+00:00"
