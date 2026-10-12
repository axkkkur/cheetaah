from __future__ import annotations

from pathlib import Path

from app.pipeline.extract import extract

TRANSCRIPT = (Path(__file__).parent / "fixtures" / "meeting1_hinglish.txt").read_text(encoding="utf-8")


def test_invalid_schema_triggers_retry(monkeypatch):
    calls = []

    def fake(system, user, tool_name, schema, max_tokens=4096):
        calls.append(user)
        if len(calls) == 1:
            return {"summary": "x", "decisions": "bad", "action_items": []}
        return {
            "summary": "ok",
            "decisions": [
                {
                    "topic": "Database",
                    "decision": "Use SQLite for MVP.",
                    "quote": "hum SQLite hi use karenge for the MVP database",
                    "speaker": "Speaker 1",
                }
            ],
            "action_items": [],
        }

    monkeypatch.setattr("app.pipeline.extract.llm_structured", fake)
    result = extract(TRANSCRIPT)
    assert len(calls) == 2
    assert "Previous attempt" in calls[1]
    assert len(result.decisions) == 1


def test_fabricated_quotes_dropped(monkeypatch):
    def fake(system, user, tool_name, schema, max_tokens=4096):
        return {
            "summary": "s",
            "decisions": [
                {
                    "topic": "Fake",
                    "decision": "Rewrite in Rust.",
                    "quote": "we will rewrite everything in rust tomorrow",
                    "speaker": None,
                },
                {
                    "topic": "Database",
                    "decision": "Use SQLite for MVP.",
                    "quote": "hum SQLite hi use karenge for the MVP database",
                    "speaker": "Speaker 1",
                },
            ],
            "action_items": [],
        }

    monkeypatch.setattr("app.pipeline.extract.llm_structured", fake)
    result = extract(TRANSCRIPT)
    # first attempt has fabricated quote → retry; second same → drop bad
    assert all("rust" not in d.quote.lower() for d in result.decisions)
    assert any("SQLite" in d.quote for d in result.decisions)
