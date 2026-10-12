from __future__ import annotations

import pytest

from app.db import db, init_db, now


@pytest.fixture()
def fresh(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cheetaah_data", str(tmp_path))
    monkeypatch.setattr(settings, "cheetaah_repo", str(tmp_path / "repo"))
    init_db()
    yield


def _insert_item(kind="doc_change", status="proposed"):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO meetings (title, status, created_at) VALUES (?, ?, ?)",
            ("t", "awaiting_approval", now()),
        )
        mid = cur.lastrowid
        cur = conn.execute(
            """
            INSERT INTO action_items
            (meeting_id, title, kind, instruction, target_paths, quote, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mid, "Update README", kind, "Edit README.md", "[]", "update readme please now", status, now()),
        )
        return cur.lastrowid


def test_execute_refuses_proposed(fresh, monkeypatch):
    item_id = _insert_item(status="proposed")
    called = {"n": 0}
    monkeypatch.setattr(
        "app.execution.executor.run_antigravity",
        lambda **k: called.__setitem__("n", called["n"] + 1),
    )
    monkeypatch.setattr(
        "app.execution.executor.create_worktree",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no wt")),
    )
    from app.execution.executor import execute_item

    execute_item(item_id)
    assert called["n"] == 0
    with db() as conn:
        row = conn.execute("SELECT status FROM action_items WHERE id = ?", (item_id,)).fetchone()
        events = conn.execute(
            "SELECT event FROM audit WHERE entity='action_item' AND entity_id=? AND event='execute_refused'",
            (item_id,),
        ).fetchall()
    assert row["status"] == "proposed"
    assert events


def test_execute_refuses_rejected(fresh, monkeypatch):
    item_id = _insert_item(status="rejected")
    monkeypatch.setattr(
        "app.execution.executor.run_antigravity",
        lambda **k: (_ for _ in ()).throw(AssertionError()),
    )
    from app.execution.executor import execute_item

    execute_item(item_id)
    with db() as conn:
        row = conn.execute("SELECT status FROM action_items WHERE id = ?", (item_id,)).fetchone()
    assert row["status"] == "rejected"


def test_execute_refuses_approved_without_row(fresh, monkeypatch):
    item_id = _insert_item(status="approved")
    monkeypatch.setattr(
        "app.execution.executor.run_antigravity",
        lambda **k: (_ for _ in ()).throw(AssertionError()),
    )
    from app.execution.executor import execute_item

    execute_item(item_id)
    with db() as conn:
        row = conn.execute("SELECT status FROM action_items WHERE id = ?", (item_id,)).fetchone()
        events = conn.execute(
            "SELECT event FROM audit WHERE entity_id=? AND event='execute_refused'",
            (item_id,),
        ).fetchall()
    assert row["status"] == "approved"
    assert events


def test_task_only_never_executes(fresh, monkeypatch):
    item_id = _insert_item(kind="task_only", status="approved")
    with db() as conn:
        conn.execute(
            "INSERT INTO approvals (item_id, decision, ts) VALUES (?, 'approved', ?)",
            (item_id, now()),
        )
    monkeypatch.setattr(
        "app.execution.executor.run_antigravity",
        lambda **k: (_ for _ in ()).throw(AssertionError()),
    )
    monkeypatch.setattr(
        "app.execution.executor.create_worktree",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError()),
    )
    from app.execution.executor import execute_item

    execute_item(item_id)
    with db() as conn:
        row = conn.execute("SELECT status, result FROM action_items WHERE id = ?", (item_id,)).fetchone()
    assert row["status"] == "failed"
    assert "No handler" in (row["result"] or "")
