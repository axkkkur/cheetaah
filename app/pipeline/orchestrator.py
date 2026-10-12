from __future__ import annotations

import json
import traceback
from typing import Callable

from app.db import audit, db, now
from app.pipeline.extract import extract
from app.pipeline.memory import check_memory
from app.pipeline.transcribe import transcribe


def step_transcribe(meeting_id: int) -> None:
    with db() as conn:
        row = conn.execute("SELECT audio_path FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not row or not row["audio_path"]:
            raise RuntimeError("Meeting has no audio_path")
        audio_path = row["audio_path"]
    text = transcribe(audio_path)
    with db() as conn:
        conn.execute(
            "UPDATE meetings SET transcript = ? WHERE id = ?",
            (text, meeting_id),
        )


def step_extract(meeting_id: int) -> None:
    with db() as conn:
        row = conn.execute("SELECT transcript FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not row or not row["transcript"]:
            raise RuntimeError("Meeting has no transcript")
        transcript = row["transcript"]

    extraction = extract(transcript)
    decided_at = now()
    with db() as conn:
        conn.execute(
            "UPDATE meetings SET summary = ? WHERE id = ?",
            (extraction.summary, meeting_id),
        )
        for d in extraction.decisions:
            conn.execute(
                """
                INSERT INTO decisions (meeting_id, topic, decision, quote, speaker, decided_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (meeting_id, d.topic, d.decision, d.quote, d.speaker, decided_at),
            )
        for a in extraction.action_items:
            conn.execute(
                """
                INSERT INTO action_items
                (meeting_id, title, owner, due, kind, instruction, target_paths, quote, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?)
                """,
                (
                    meeting_id,
                    a.title,
                    a.owner,
                    a.due,
                    a.kind,
                    a.instruction,
                    json.dumps(a.target_paths),
                    a.quote,
                    decided_at,
                ),
            )


def step_memory(meeting_id: int) -> None:
    with db() as conn:
        row = conn.execute("SELECT transcript FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        transcript = (row["transcript"] if row else "") or ""
    check_memory(meeting_id, transcript)


PIPELINE: list[tuple[str, str, Callable[[int], None]]] = [
    ("transcribing", "transcribe", step_transcribe),
    ("extracting", "extract", step_extract),
    ("checking_memory", "memory", step_memory),
]


def run_intake(meeting_id: int) -> None:
    try:
        for status, event, fn in PIPELINE:
            with db() as conn:
                conn.execute(
                    "UPDATE meetings SET status = ?, error = NULL WHERE id = ?",
                    (status, meeting_id),
                )
                audit("meeting", meeting_id, f"{event}_start", conn=conn)
            fn(meeting_id)
            audit("meeting", meeting_id, f"{event}_done")
        with db() as conn:
            conn.execute(
                "UPDATE meetings SET status = ? WHERE id = ?",
                ("awaiting_approval", meeting_id),
            )
            audit("meeting", meeting_id, "awaiting_approval", conn=conn)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        with db() as conn:
            conn.execute(
                "UPDATE meetings SET status = ?, error = ? WHERE id = ?",
                ("failed", err, meeting_id),
            )
            audit(
                "meeting",
                meeting_id,
                "failed",
                {"error": err, "trace": traceback.format_exc()},
                conn=conn,
            )
